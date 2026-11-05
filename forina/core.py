import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import uuid
import zipfile
from contextlib import contextmanager

from .compliance import ComplianceRegister
from .enrollment import EnrollmentEngine
from .url_registry import DomainRegistry

ROOT = Path(__file__).resolve().parent
GUARDRAILS = ROOT / 'vendor/guardrails'

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()

def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def text(value, name, limit=200):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'{name}: Text mit 1–{limit} Zeichen erforderlich')
    return value.strip()

def guardrails(command, *args):
    result = subprocess.run([sys.executable, str(GUARDRAILS / 'forina.py'), command, *args], capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise ValueError(result.stderr.strip())
    return json.loads(result.stdout)

class Workbench:
    def __init__(self, storage):
        self.storage = Path(storage)
        self.storage.mkdir(parents=True, exist_ok=True)
        self.catalog = json.loads((ROOT / 'data/catalog.json').read_text())
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS organizations (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
        self.compliance = ComplianceRegister(self.db)
        self.enrollment = EnrollmentEngine(self.db, self.storage, self.organization, self.compliance)
        self.registry = DomainRegistry(self.db)

    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.storage / 'forina.sqlite3', timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def projects(self):
        return self.catalog['projects']

    def search(self, query):
        query = text(query, 'Suchbegriff', 200).casefold()
        found = []
        for doc in self.catalog['documents']:
            offset = doc['text'].casefold().find(query)
            if offset < 0 and query not in doc['path'].casefold():
                continue
            offset = max(0, offset - 100)
            found.append({k: v for k, v in doc.items() if k != 'text'} | {'excerpt': doc['text'][offset:offset + 650]})
        return {'total': len(found), 'results': found[:60], 'scope': 'Dateipfade und begrenzte Textauszüge; keine vollständige semantische Analyse'}

    def organizations(self):
        with self.db() as db:
            return [json.loads(row[0]) for row in db.execute('SELECT data FROM organizations ORDER BY rowid DESC')]

    def organization(self, oid):
        with self.db() as db:
            row = db.execute('SELECT data FROM organizations WHERE id=?', (oid,)).fetchone()
        if row is None:
            raise KeyError('Organisation nicht gefunden')
        return json.loads(row[0])

    def add_organization(self, body):
        name = text(body.get('name'), 'Organisationsname')
        domain = text(body.get('domain'), 'Domain', 253)
        sector = body.get('sector', 'general')
        if sector not in {'general', 'finance', 'critical', 'crypto', 'platform', 'ai', 'government'}:
            raise ValueError('Unbekannter Sektor')
        codes = body.get('jurisdictions', ['EU'])
        if not isinstance(codes, list) or not 1 <= len(codes) <= 21:
            raise ValueError('Rechtsräume müssen eine nichtleere Liste sein')
        countries = json.loads((GUARDRAILS / 'jurisdictions.json').read_text())
        if any(not isinstance(c, str) or c.upper() not in countries for c in codes):
            raise ValueError('Unbekannter Rechtsraum')
        codes = sorted(set(c.upper() for c in codes))
        # Domain validation and policy behavior are delegated to the original adapter.
        plan = guardrails('plan', '--jurisdiction', *codes, '--domain', domain, '--sector', sector)
        lei = body.get('lei', '')
        if not isinstance(lei, str) or (lei and not re.fullmatch(r'[A-Z0-9]{20}', lei)):
            raise ValueError('LEI muss leer oder eine 20-stellige Großbuchstaben-/Ziffernfolge sein')
        org = {'id': str(uuid.uuid4()), 'name': name, 'domain': plan['hosts'][0]['hostname'], 'sector': sector, 'jurisdictions': codes, 'lei': lei, 'created_utc': now(), 'identity_status': 'UNVERIFIED', 'lei_status': 'UNVERIFIED' if lei else 'NOT_PROVIDED', 'domain_status': 'UNVERIFIED', 'federation_status': 'NOT_ENROLLED'}
        with self.db() as db:
            db.execute('INSERT INTO organizations VALUES (?,?)', (org['id'], json.dumps(org)))
        return org

    def plan(self, oid):
        org = self.organization(oid)
        plan = guardrails('plan', '--jurisdiction', *org['jurisdictions'], '--domain', org['domain'], '--sector', org['sector'])
        plan['compliance_register'] = self.compliance.snapshot(org)
        return plan

    def challenge(self, oid, reference):
        org = self.organization(oid)
        return guardrails('challenge', '--domain', org['domain'], '--authorization-reference', text(reference, 'Freigabereferenz'))

    def records(self):
        with self.db() as db:
            return [json.loads(row[0]) for row in db.execute('SELECT data FROM records ORDER BY rowid DESC')]

    def record(self, rid):
        with self.db() as db:
            row = db.execute('SELECT data FROM records WHERE id=?', (rid,)).fetchone()
        if row is None:
            raise KeyError('Nachweis nicht gefunden')
        return json.loads(row[0])

    def create_record(self, oid):
        org = self.organization(oid)
        plan = self.plan(oid)
        compliance = plan.pop('compliance_register')
        sources = [{'archive': p['archive'], 'sha256': p['archive_sha256'], 'role': p['role']} for p in self.projects()]
        components = {'organization': org, 'policy_plan': plan, 'sources': sources, 'compliance_register': compliance}
        hashes = {key: digest(value) for key, value in components.items()}
        record = {'id': str(uuid.uuid4()), 'created_utc': now(), 'schema_version': 2, 'status': 'DRAFT_REQUIRES_REVIEW', 'signed': False, 'access_granted': False, 'components': components, 'component_hashes': hashes, 'bundle_sha256': digest(hashes), 'integrity_scope': 'SHA-256-Konsistenz; keine Signatur, externe Beglaubigung oder Unveränderlichkeit'}
        with self.db() as db:
            db.execute('INSERT INTO records VALUES (?,?)', (record['id'], json.dumps(record)))
        return record

    def export(self, rid):
        record = self.record(rid)
        target = io.BytesIO()
        with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('record.json', canonical(record))
            for name, value in record['components'].items():
                archive.writestr(name + '.json', canonical(value))
            archive.writestr('README.txt', 'Forina-Prüfentwurf. Kein Zertifikat, keine Signatur, keine Zugangsfreigabe.\nHash-Prüfung erkennt Inkonsistenzen, nicht das Neuberechnen aller Hashes durch Dritte.\n')
        return target.getvalue()

def verify_record(record):
    if not isinstance(record, dict) or not isinstance(record.get('components'), dict):
        raise ValueError('Ungültiges Nachweisschema')
    expected = {'organization', 'policy_plan', 'sources'}
    if record.get('schema_version') == 2:
        expected.add('compliance_register')
    elif record.get('schema_version') != 1:
        raise ValueError('Unbekannte Nachweisschemaversion')
    if set(record['components']) != expected:
        raise ValueError('Ungültige Nachweiskomponenten')
    hashes = {k: digest(v) for k, v in record['components'].items()}
    valid = hashes == record.get('component_hashes') and digest(hashes) == record.get('bundle_sha256')
    return {'consistent': valid, 'signature_verified': False, 'scope': 'Komponenten und Bundle-Hash; Metadaten und Herkunft nicht authentifiziert'}
