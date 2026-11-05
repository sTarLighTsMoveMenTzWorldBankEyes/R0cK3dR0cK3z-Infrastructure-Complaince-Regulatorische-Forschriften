"""Offline FTEP tests: fixture proof, test signatures, expiry, replay and revocation."""
import base64
import copy
from concurrent.futures import ThreadPoolExecutor
import json
import tempfile
import unittest

from forina.core import Workbench
from forina.intake import fingerprint


class EnrollmentTests(unittest.TestCase):
    def setUp(self):
        self.storage = tempfile.TemporaryDirectory(prefix='forina-ftep-test-')
        self.addCleanup(self.storage.cleanup)
        self.workbench = Workbench(self.storage.name)
        self.engine = self.workbench.enrollment
        self.time = 1_900_000_000
        self.engine.clock = lambda: self.time
        self.organization = self.workbench.add_organization({
            'name': 'Synthetic FTEP organization', 'domain': 'example.org',
            'jurisdictions': ['EU'], 'sector': 'finance',
        })

    def start(self, **changes):
        return self.engine.start({
            'organization_id': self.organization['id'],
            'test_consent': True,
            'authorization_reference': 'SYNTHETIC-AUTHORIZATION-001',
            **changes,
        })

    def fixture(self, enrollment):
        return {'fixture': {
            'name': enrollment['challenge']['dns_name'],
            'value': enrollment['challenge']['txt_value'],
        }}

    def issue(self):
        enrollment = self.start()
        issued = self.engine.simulate(enrollment['id'], self.fixture(enrollment))
        return enrollment, issued

    def assert_invalid_signature(self, envelope, engine=None):
        try:
            result = (engine or self.engine).verify(envelope)
        except ValueError:
            return
        self.assertFalse(result['signature_valid'])
        self.assertFalse(result['usable_for_test'])

    def test_explicit_test_consent_and_reference_are_required(self):
        for changes in [
            {'test_consent': False}, {'test_consent': None}, {'test_consent': 1},
            {'authorization_reference': ''}, {'authorization_reference': 'short'},
            {'authorization_reference': None},
        ]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.start(**changes)
        with self.assertRaises((ValueError, KeyError)):
            self.start(organization_id='unknown-organization')

    def test_server_bounds_challenge_lifetime(self):
        for ttl in [59, 901, -1, True, 60.5, '60']:
            with self.subTest(ttl=ttl), self.assertRaises(ValueError):
                self.start(ttl_seconds=ttl)
        enrollment = self.start(ttl_seconds=60)
        self.assertEqual(enrollment['challenge']['expires_at'], self.time + 60)
        self.assertEqual(enrollment['state'], 'CHALLENGE_ISSUED')
        self.assertFalse(enrollment['real_domain_verified'])
        self.assertFalse(enrollment['access_granted'])
        self.assertTrue(enrollment['challenge']['dns_name'].endswith('.example.org'))
        self.assertFalse(enrollment['challenge']['dns_name'].startswith('_acme-challenge.'))

    def test_tokens_are_unique_and_only_returned_at_creation(self):
        first, second = self.start(), self.start()
        self.assertNotEqual(first['challenge']['id'], second['challenge']['id'])
        self.assertNotEqual(first['challenge']['txt_value'], second['challenge']['txt_value'])
        for result in [self.engine.get(first['id']), self.engine.list()]:
            encoded = json.dumps(result)
            self.assertNotIn('txt_value', encoded)
            self.assertNotIn(first['challenge']['txt_value'], encoded)
            self.assertNotIn(second['challenge']['txt_value'], encoded)

    def test_wrong_fixture_does_not_consume_valid_challenge(self):
        enrollment = self.start()
        correct = self.fixture(enrollment)
        for fixture in [
            {'fixture': {'name': 'wrong.example.org', 'value': correct['fixture']['value']}},
            {'fixture': {'name': correct['fixture']['name'], 'value': 'wrong-value'}},
            {'fixture': {}}, {},
        ]:
            with self.subTest(fixture=fixture), self.assertRaises(ValueError):
                self.engine.simulate(enrollment['id'], fixture)
        self.assertEqual(self.engine.simulate(enrollment['id'], correct)['state'], 'TEST_RECEIPT_ISSUED')

    def test_challenge_is_bound_to_its_enrollment(self):
        first, second = self.start(), self.start()
        with self.assertRaises(ValueError):
            self.engine.simulate(second['id'], self.fixture(first))
        issued = self.engine.simulate(second['id'], self.fixture(second))
        self.assertEqual(issued['receipt']['payload']['enrollment_id'], second['id'])

    def test_expired_challenge_is_rejected_at_exact_boundary(self):
        enrollment = self.start(ttl_seconds=60)
        self.time = enrollment['challenge']['expires_at']
        with self.assertRaises(ValueError):
            self.engine.simulate(enrollment['id'], self.fixture(enrollment))

    def test_challenge_cannot_be_replayed(self):
        enrollment, issued = self.issue()
        with self.assertRaises(ValueError):
            self.engine.simulate(enrollment['id'], self.fixture(enrollment))
        persisted = self.engine.get(enrollment['id'])
        self.assertEqual(persisted['receipt'], issued['receipt'])

    def test_concurrent_reuse_issues_exactly_one_receipt(self):
        enrollment = self.start()
        fixture = self.fixture(enrollment)

        def attempt(_):
            try:
                return self.engine.simulate(enrollment['id'], fixture)
            except ValueError:
                return None

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(attempt, range(2)))
        successes = [outcome for outcome in outcomes if outcome is not None]
        self.assertEqual(len(successes), 1)
        self.assertEqual(self.engine.get(enrollment['id'])['receipt'], successes[0]['receipt'])

    def test_signed_test_claims_never_grant_real_verification_or_access(self):
        enrollment, issued = self.issue()
        envelope = issued['receipt']
        self.assertEqual(set(envelope), {'protected', 'payload', 'signature'})
        header, payload = envelope['protected'], envelope['payload']
        self.assertEqual(header['typ'], 'FTEP-LOCAL-TEST')
        self.assertEqual(header['alg'], 'Ed25519')
        self.assertEqual(header['version'], 1)
        self.assertEqual(header['kid'], self.engine.key_info()['kid'])
        self.assertEqual(len(base64.b64decode(envelope['signature'], validate=True)), 64)
        self.assertEqual(payload['purpose'], 'FORINA_LOCAL_TEST_ONLY')
        self.assertEqual(payload['domain_control'], 'SIMULATED_CONTROL_CONFIRMED')
        self.assertEqual(payload['domain'], 'example.org')
        self.assertEqual(payload['organization_id'], self.organization['id'])
        self.assertEqual(payload['enrollment_id'], enrollment['id'])
        self.assertEqual(payload['issued_at'], self.time)
        self.assertGreater(payload['expires_at'], self.time)
        for claim in ['identity_verified', 'compliance_verified', 'access_granted']:
            self.assertIs(payload[claim], False)
        result = self.engine.verify(envelope)
        self.assertTrue(result['signature_valid'])
        self.assertTrue(result['time_valid'])
        self.assertTrue(result['status_known'])
        self.assertFalse(result['revoked'])
        self.assertTrue(result['usable_for_test'])
        self.assertFalse(result['access_granted'])
        self.assertFalse(result['trusted_for_federation'])
        persisted = self.workbench.organization(self.organization['id'])
        self.assertEqual(persisted['domain_status'], 'UNVERIFIED')
        self.assertEqual(persisted['identity_status'], 'UNVERIFIED')
        self.assertEqual(persisted['federation_status'], 'NOT_ENROLLED')

    def test_payload_and_protected_header_are_signature_bound(self):
        _, issued = self.issue()
        original = issued['receipt']
        mutations = [
            ('payload', 'domain', 'other.example.org'),
            ('payload', 'access_granted', True),
            ('payload', 'identity_verified', True),
            ('payload', 'purpose', 'PRODUCTION'),
            ('protected', 'alg', 'none'),
            ('protected', 'kid', 'attacker-key'),
            ('protected', 'typ', 'FTEP-PRODUCTION'),
            ('protected', 'version', 2),
        ]
        for section, key, value in mutations:
            with self.subTest(section=section, key=key):
                changed = copy.deepcopy(original)
                changed[section][key] = value
                self.assert_invalid_signature(changed)
        extra = copy.deepcopy(original)
        extra['access_granted'] = True
        self.assert_invalid_signature(extra)
        malformed = copy.deepcopy(original)
        malformed['signature'] = 'invalid-base64!'
        self.assert_invalid_signature(malformed)

    def test_different_test_key_cannot_assert_local_trust(self):
        _, issued = self.issue()
        with tempfile.TemporaryDirectory(prefix='forina-other-issuer-') as storage:
            other = Workbench(storage).enrollment
            other.clock = lambda: self.time
            self.assertNotEqual(self.engine.key_info()['kid'], other.key_info()['kid'])
            self.assert_invalid_signature(issued['receipt'], engine=other)
            substituted = copy.deepcopy(issued['receipt'])
            substituted['public_key_pem'] = self.engine.key_info()['public_key_pem']
            self.assert_invalid_signature(substituted, engine=other)

    def test_receipt_expiry_is_distinct_from_signature_validity(self):
        _, issued = self.issue()
        self.time = issued['receipt']['payload']['expires_at']
        result = self.engine.verify(issued['receipt'])
        self.assertTrue(result['signature_valid'])
        self.assertFalse(result['time_valid'])
        self.assertFalse(result['usable_for_test'])
        self.assertFalse(result['access_granted'])

    def test_signed_but_unregistered_receipt_is_not_usable(self):
        enrollment, issued = self.issue()
        with self.workbench.db() as db:
            db.execute('DELETE FROM ftep_enrollments WHERE id=?', (enrollment['id'],))
        result = self.engine.verify(issued['receipt'])
        self.assertTrue(result['signature_valid'])
        self.assertTrue(result['time_valid'])
        self.assertFalse(result['status_known'])
        self.assertFalse(result['usable_for_test'])
        self.assertFalse(result['access_granted'])
        self.assertFalse(result['trusted_for_federation'])

    def test_source_change_does_not_make_old_receipt_a_compliance_attestation(self):
        _, issued = self.issue()
        envelope = issued['receipt']
        old_snapshot_hash = envelope['payload']['compliance_snapshot_sha256']
        body = {'title':'Synthetic FTEP source update.md', 'content':'DSGVO Artikel 5: synthetic new source revision.'}
        preview = self.workbench.compliance.preview(body)
        self.workbench.compliance.ingest_document({**body, 'preview_digest':preview['preview_digest'], 'expected_digest':preview['replaces_digest']})
        new_snapshot = self.workbench.compliance.snapshot(self.organization)
        self.assertNotEqual(old_snapshot_hash, fingerprint(new_snapshot))
        self.assertEqual(envelope['payload']['compliance_snapshot_sha256'], old_snapshot_hash)
        for flag in ['identity_verified', 'compliance_verified', 'access_granted']:
            self.assertIs(envelope['payload'][flag], False)
        result = self.engine.verify(envelope)
        self.assertTrue(result['signature_valid'])
        self.assertFalse(result['access_granted'])
        self.assertFalse(result['trusted_for_federation'])
        organization = self.workbench.organization(self.organization['id'])
        self.assertEqual(organization['identity_status'], 'UNVERIFIED')
        self.assertEqual(organization['domain_status'], 'UNVERIFIED')

    def test_revocation_is_independent_from_signature_validity(self):
        enrollment, issued = self.issue()
        with self.assertRaises(ValueError):
            self.engine.revoke(enrollment['id'], {'reason': ''})
        revoked = self.engine.revoke(enrollment['id'], {'reason': 'Synthetic withdrawal of test consent'})
        self.assertEqual(revoked['state'], 'REVOKED')
        result = self.engine.verify(issued['receipt'])
        self.assertTrue(result['signature_valid'])
        self.assertTrue(result['status_known'])
        self.assertTrue(result['revoked'])
        self.assertFalse(result['usable_for_test'])
        self.assertFalse(result['trusted_for_federation'])
        self.assertFalse(result['access_granted'])

    def test_revocation_before_simulation_prevents_issuance(self):
        enrollment = self.start()
        self.engine.revoke(enrollment['id'], {'reason': 'Synthetic cancellation'})
        with self.assertRaises(ValueError):
            self.engine.simulate(enrollment['id'], self.fixture(enrollment))

    def test_restart_preserves_test_key_receipt_and_revocation(self):
        enrollment, issued = self.issue()
        before = self.engine.key_info()
        self.assertEqual(before['profile'], 'TEST_ONLY')
        self.assertIn('BEGIN PUBLIC KEY', before['public_key_pem'])
        self.assertNotIn('PRIVATE KEY', json.dumps(before))
        self.engine.revoke(enrollment['id'], {'reason': 'Synthetic revocation before restart'})
        restarted = Workbench(self.storage.name).enrollment
        restarted.clock = lambda: self.time
        self.assertEqual(restarted.key_info(), before)
        self.assertEqual(restarted.get(enrollment['id'])['state'], 'REVOKED')
        verified = restarted.verify(issued['receipt'])
        self.assertTrue(verified['signature_valid'])
        self.assertTrue(verified['revoked'])
        self.assertFalse(verified['usable_for_test'])


if __name__ == '__main__':
    unittest.main()
