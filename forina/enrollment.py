"""FTEP local test profile: offline DNS fixtures and pinned Ed25519 test receipts.

This module never queries or changes DNS, validates a legal identity, or grants access.
The envelope is a Forina-specific test format, not ACME, JWS, or OpenID Federation.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
import uuid

from .compliance import RevisionConflict, required
from .intake import encoded, fingerprint

class EnrollmentConflict(RevisionConflict):
    pass

class TestSigner:
    def __init__(self, storage):
        self.path = Path(storage) / 'ftep-test-key.pem'
        self.lock = threading.Lock()
        self.material = None

    def _openssl(self, *args):
        if not shutil.which('openssl'):
            raise RuntimeError('FTEP-Testsignaturen benötigen OpenSSL 3 mit Ed25519-Unterstützung')
        result = subprocess.run(['openssl', *map(str, args)], capture_output=True, timeout=15)
        if result.returncode:
            # Never echo key material, input payloads, or tool stderr into API/logs.
            raise RuntimeError('OpenSSL-Testschlüsseloperation fehlgeschlagen')
        return result.stdout

    def key_info(self):
        with self.lock:
            if self.material is None:
                if self.path.is_symlink():
                    raise RuntimeError('Verknüpfte Testschlüsseldatei ist nicht zulässig')
                if not self.path.exists():
                    with tempfile.TemporaryDirectory(dir=self.path.parent, prefix='ftep-key-') as tmp:
                        candidate = Path(tmp) / 'key.pem'
                        self._openssl('genpkey', '-algorithm', 'ED25519', '-out', candidate)
                        candidate.chmod(0o600)
                        try:
                            # Atomic no-overwrite publication across processes.
                            os.link(candidate, self.path)
                        except FileExistsError:
                            pass
                if self.path.is_symlink() or not self.path.is_file() or self.path.stat().st_mode & 0o077:
                    raise RuntimeError('Testschlüssel muss eine private reguläre Datei mit Modus 0600 sein')
                der = self._openssl('pkey', '-in', self.path, '-pubout', '-outform', 'DER')
                if len(der) != 44 or der[:12] != bytes.fromhex('302a300506032b6570032100'):
                    raise RuntimeError('Persistierter Testschlüssel ist kein Ed25519-Schlüssel')
                public = self._openssl('pkey', '-in', self.path, '-pubout').decode('ascii')
                self.material = {'profile':'TEST_ONLY', 'kid':hashlib.sha256(der).hexdigest(), 'public_key_pem':public, 'algorithm':'Ed25519'}
        return dict(self.material)

    def sign(self, payload):
        info = self.key_info()
        protected = {'typ':'FTEP-LOCAL-TEST', 'alg':'Ed25519', 'kid':info['kid'], 'version':1}
        envelope = {'protected':protected, 'payload':payload}
        with tempfile.TemporaryDirectory(dir=self.path.parent, prefix='ftep-sign-') as tmp:
            body, signature = Path(tmp) / 'payload.json', Path(tmp) / 'signature.bin'
            body.write_bytes(encoded(envelope))
            self._openssl('pkeyutl', '-sign', '-rawin', '-inkey', self.path, '-in', body, '-out', signature)
            envelope['signature'] = base64.b64encode(signature.read_bytes()).decode('ascii')
        if not self.verify(envelope):
            raise RuntimeError('Testsignatur passt nicht zum lokal gepinnten Schlüssel')
        return envelope

    def verify(self, envelope):
        info = self.key_info()
        if not isinstance(envelope, dict) or set(envelope) != {'protected', 'payload', 'signature'}:
            return False
        if envelope['protected'] != {'typ':'FTEP-LOCAL-TEST', 'alg':'Ed25519', 'kid':info['kid'], 'version':1} or not isinstance(envelope['payload'], dict):
            return False
        if not isinstance(envelope['signature'], str) or len(envelope['signature']) != 88:
            return False
        try:
            signature = base64.b64decode(envelope['signature'], validate=True)
        except ValueError:
            return False
        if len(signature) != 64:
            return False
        with tempfile.TemporaryDirectory(dir=self.path.parent, prefix='ftep-verify-') as tmp:
            public, body, sig = (Path(tmp) / name for name in ('public.pem', 'payload.json', 'signature.bin'))
            public.write_text(info['public_key_pem'])
            body.write_bytes(encoded({k:envelope[k] for k in ('protected','payload')}))
            sig.write_bytes(signature)
            result = subprocess.run(['openssl', 'pkeyutl', '-verify', '-pubin', '-inkey', str(public), '-rawin', '-in', str(body), '-sigfile', str(sig)], capture_output=True, timeout=15)
        return result.returncode == 0

class EnrollmentEngine:
    def __init__(self, connect, storage, organization, compliance, clock=time.time):
        self.connect, self.organization, self.compliance, self.clock = connect, organization, compliance, clock
        self.signer = TestSigner(storage)
        with connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS ftep_enrollments (id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS ftep_events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL);
            ''')

    def key_info(self):
        return self.signer.key_info()

    def _read(self, db, enrollment_id):
        row = db.execute('SELECT data FROM ftep_enrollments WHERE id=?', (enrollment_id,)).fetchone()
        if row is None:
            raise KeyError('FTEP-Testvorgang nicht gefunden')
        return json.loads(row[0])

    def _write(self, db, data, action):
        db.execute('INSERT OR REPLACE INTO ftep_enrollments VALUES (?,?)', (data['id'], encoded(data).decode()))
        # No TXT tokens, fixture contents, private key material or personal names.
        event = {'at':int(self.clock()), 'enrollment_id':data['id'], 'action':action, 'profile':'TEST_ONLY'}
        db.execute('INSERT INTO ftep_events(data) VALUES (?)', (encoded(event).decode(),))

    def _public(self, row):
        result = {k:v for k,v in row.items() if k != 'txt_sha256'}
        if row['state'] == 'CHALLENGE_ISSUED' and row['challenge']['expires_at'] <= int(self.clock()):
            result['state'] = 'EXPIRED'
        if row['state'] == 'TEST_RECEIPT_ISSUED' and row['receipt']['payload']['expires_at'] <= int(self.clock()):
            result['state'] = 'EXPIRED'
        return result

    def list(self):
        with self.connect() as db:
            return [self._public(json.loads(r[0])) for r in db.execute('SELECT data FROM ftep_enrollments ORDER BY rowid DESC')]

    def get(self, enrollment_id):
        with self.connect() as db:
            return self._public(self._read(db, enrollment_id))

    def start(self, body):
        if body.get('test_consent') is not True:
            raise ValueError('Explizite Zustimmung zur lokalen Simulation ist erforderlich')
        reference = required(body.get('authorization_reference'), 'Test-Freigabereferenz', 200)
        if len(reference) < 8:
            raise ValueError('Test-Freigabereferenz muss mindestens 8 Zeichen umfassen')
        ttl = body.get('ttl_seconds', 300)
        if type(ttl) is not int or not 60 <= ttl <= 900:
            raise ValueError('Challenge-Laufzeit muss 60 bis 900 Sekunden betragen')
        org = self.organization(required(body.get('organization_id'), 'Organisationskennung', 100))
        now = int(self.clock())
        value = 'forina-test-v1=' + secrets.token_urlsafe(32)
        challenge = {'id':str(uuid.uuid4()), 'dns_name':'_forina-test-challenge.' + org['domain'], 'issued_at':now, 'expires_at':now+ttl}
        row = {'id':str(uuid.uuid4()), 'protocol':'FTEP-LOCAL-0.1', 'profile':'TEST_ONLY', 'state':'CHALLENGE_ISSUED',
            'organization_id':org['id'], 'domain':org['domain'], 'authorization_reference':reference,
            'authorization_status':'SELF_DECLARED_TEST_CONSENT', 'challenge':challenge,
            'txt_sha256':hashlib.sha256(value.encode()).hexdigest(), 'receipt':None, 'revocation':None,
            'real_domain_verified':False, 'identity_verified':False, 'compliance_verified':False,
            'federation_status':'TEST_ONLY_NOT_ENROLLED', 'access_granted':False}
        with self.connect() as db:
            self._write(db, row, 'TEST_CHALLENGE_CREATED')
        return {**self._public(row), 'challenge':{**challenge, 'txt_value':value}}

    def simulate(self, enrollment_id, body):
        fixture = body.get('fixture')
        if not isinstance(fixture, dict) or set(fixture) != {'name', 'value'} or not all(isinstance(fixture[k], str) for k in ('name','value')):
            raise ValueError('DNS-Testfixture mit name und value erforderlich; keine Live-DNS-Prüfung')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self._read(db, enrollment_id)
            if row['state'] != 'CHALLENGE_ISSUED':
                raise EnrollmentConflict('Test-Challenge wurde bereits verwendet oder widerrufen')
            now = int(self.clock())
            if now >= row['challenge']['expires_at']:
                raise EnrollmentConflict('Test-Challenge ist abgelaufen; neuen Vorgang beginnen')
            org = self.organization(row['organization_id'])
            if org['domain'] != row['domain']:
                raise EnrollmentConflict('Organisationsdomain wurde geändert; neue Challenge erforderlich')
            matches = fixture['name'].rstrip('.').lower() == row['challenge']['dns_name']
            if not matches or not secrets.compare_digest(hashlib.sha256(fixture['value'].encode()).hexdigest(), row['txt_sha256']):
                raise ValueError('DNS-Fixture stimmt nicht mit der Test-Challenge überein')
            snapshot = self.compliance.snapshot(org)
            payload = {'id':str(uuid.uuid4()), 'purpose':'FORINA_LOCAL_TEST_ONLY', 'enrollment_id':row['id'],
                'organization_id':row['organization_id'], 'domain':row['domain'], 'challenge_id':row['challenge']['id'],
                'issued_at':now, 'expires_at':now+3600, 'domain_control':'SIMULATED_CONTROL_CONFIRMED',
                'real_domain_verified':False, 'identity_verified':False, 'compliance_verified':False,
                'federation_status':'TEST_ONLY_NOT_ENROLLED', 'access_granted':False,
                'authorization_status':'SELF_DECLARED_TEST_CONSENT', 'organization_snapshot_sha256':fingerprint(org),
                'compliance_snapshot_sha256':fingerprint(snapshot)}
            row.update(state='TEST_RECEIPT_ISSUED', receipt=self.signer.sign(payload))
            row['challenge']['consumed_at'] = now
            self._write(db, row, 'SIMULATION_RECEIPT_ISSUED')
        return self._public(row)

    def revoke(self, enrollment_id, body):
        reason = required(body.get('reason'), 'Widerrufsgrund', 500)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self._read(db, enrollment_id)
            if row['state'] != 'REVOKED':
                row.update(state='REVOKED', revocation={'at':int(self.clock()), 'reason':reason})
                self._write(db, row, 'TEST_ENROLLMENT_REVOKED')
        return self._public(row)

    def verify(self, envelope):
        signature_valid = self.signer.verify(envelope)
        payload = envelope.get('payload') if isinstance(envelope, dict) else None
        time_valid = False
        profile_valid = False
        row, known, revoked = None, False, False
        if isinstance(payload, dict):
            now = int(self.clock())
            issued, expiry = payload.get('issued_at'), payload.get('expires_at')
            time_valid = type(issued) is int and type(expiry) is int and issued <= now < expiry and 0 < expiry-issued <= 3600
            profile_valid = payload.get('purpose') == 'FORINA_LOCAL_TEST_ONLY' and payload.get('domain_control') == 'SIMULATED_CONTROL_CONFIRMED' and payload.get('federation_status') == 'TEST_ONLY_NOT_ENROLLED' and all(payload.get(k) is False for k in ('real_domain_verified','identity_verified','compliance_verified','access_granted'))
            if signature_valid and isinstance(payload.get('enrollment_id'), str):
                with self.connect() as db:
                    try:
                        row = self._read(db, payload['enrollment_id'])
                    except KeyError:
                        pass
                known = row is not None and row['receipt'] == envelope
                revoked = known and row['state'] == 'REVOKED'
        return {'signature_valid':signature_valid, 'time_valid':time_valid, 'profile_valid':profile_valid,
            'status_known':known, 'revoked':revoked, 'usable_for_test':bool(signature_valid and profile_valid and time_valid and known and not revoked),
            'trusted_for_federation':False, 'access_granted':False,
            'scope':'Nur lokales Testprofil und lokaler Widerrufsstand; keine externe Identitäts-, Compliance- oder Zugangsprüfung'}
