"""Offline planning-policy boundaries; no real login, authorization or network."""
import copy
import unittest

from forina.gateway_policy import EXTERNAL_EVIDENCE, PROFILE, evaluate_gateway


class GatewayPolicyTests(unittest.TestCase):
    NOW = 1_900_000_000

    def context(self, external=True):
        return {
            'profile': PROFILE,
            'policy': {'issuer':'https://id.synthetic.test', 'audience':'forina', 'allowed_resources':['connector:synthetic']},
            'session': {'verification_profile':'OIDC_VERIFIER_OUTPUT', 'verified':True,
                'issuer':'https://id.synthetic.test', 'audience':'forina', 'subject':'synthetic-subject',
                'issued_at':self.NOW-30, 'expires_at':self.NOW+300, 'revoked':False, 'authentication_method':'PASSKEY'},
            'target': {'kind':'EXTERNAL_PORTAL' if external else 'OWN_SERVICE', 'resource':'connector:synthetic', 'required_scopes':['registry:read']},
            'authorization': {'verification_profile':'INDEPENDENT_AUTHORIZATION', 'verified':True,
                'subject':'synthetic-subject', 'resource':'connector:synthetic', 'scopes':['registry:read'],
                'approval_reference':'SYNTHETIC-CONSENT-001', 'expires_at':self.NOW+600, 'revoked':False},
            'evidence': {name:{'verification_profile':'INDEPENDENT_EVIDENCE', 'verified':True, 'reference':'SYNTHETIC-'+name,
                'expires_at':self.NOW+600, 'revoked':False} for name in EXTERNAL_EVIDENCE} if external else {},
        }

    def evaluate(self, context):
        result = evaluate_gateway(context, now=self.NOW)
        self.assertFalse(result['access_granted'])
        self.assertFalse(result['enforcement_implemented'])
        self.assertFalse(result['input_authenticity_verified'])
        return result

    def test_complete_assertions_only_make_a_plan_eligible(self):
        result = self.evaluate(self.context())
        self.assertEqual(result['decision'], 'ELIGIBLE_FOR_AUTHORIZED_CONNECTOR_PLAN')
        self.assertEqual(result['scope'], 'OFFLINE_PLANNING_ONLY')

    def test_own_service_still_requires_explicit_authorization(self):
        context = self.context(external=False)
        self.assertTrue(self.evaluate(context)['eligible_for_plan'])
        context['authorization']['verified'] = False
        self.assertEqual(self.evaluate(context)['decision'], 'DENY')

    def test_client_headers_cannot_create_a_verified_context(self):
        for context in [None, {}, {'X-Forwarded-User':'admin'}, {'Remote-User':'admin', 'authenticated':True}]:
            with self.subTest(context=context):
                self.assertEqual(self.evaluate(context)['decision'], 'DENY')
        context = self.context()
        context['headers'] = {'X-Forwarded-User':'admin'}
        self.assertEqual(self.evaluate(context)['decision'], 'DENY')

    def test_login_without_consent_or_evidence_denies_external_target(self):
        for field in ['authorization', 'evidence']:
            context = self.context()
            context[field] = {}
            with self.subTest(field=field):
                self.assertEqual(self.evaluate(context)['decision'], 'DENY')

    def test_discovery_metadata_and_test_profiles_do_not_authorize(self):
        context = self.context()
        context['session']['verification_profile'] = 'DISCOVERED_OIDC_METADATA'
        self.assertEqual(self.evaluate(context)['decision'], 'DENY')
        context = self.context()
        context['evidence']['domain_control']['verification_profile'] = 'FTEP_LOCAL_TEST_ONLY'
        self.assertEqual(self.evaluate(context)['decision'], 'DENY')
        context = self.context()
        context['profile'] = 'UNKNOWN'
        self.assertEqual(self.evaluate(context)['decision'], 'DENY')

    def test_issuer_audience_subject_and_resource_binding(self):
        mutations = [('session','issuer','https://other.synthetic.test'), ('session','audience','another-rp'),
                     ('authorization','subject','another-user'), ('authorization','resource','connector:other')]
        for section, field, value in mutations:
            context = self.context()
            context[section][field] = value
            with self.subTest(field=field):
                self.assertEqual(self.evaluate(context)['decision'], 'DENY')

    def test_scope_and_configured_target_are_required(self):
        context = self.context()
        context['authorization']['scopes'] = ['different:scope']
        self.assertIn('AUTHORIZATION_SCOPE_INSUFFICIENT', self.evaluate(context)['reasons'])
        context = self.context()
        context['policy']['allowed_resources'] = ['connector:other']
        self.assertIn('RESOURCE_NOT_CONFIGURED', self.evaluate(context)['reasons'])

    def test_exact_expiry_boundary_and_future_session(self):
        for section, field in [('session','expires_at'), ('authorization','expires_at')]:
            context = self.context()
            context[section][field] = self.NOW
            with self.subTest(section=section):
                self.assertEqual(self.evaluate(context)['decision'], 'DENY')
        context = self.context()
        context['session']['issued_at'] = self.NOW+1
        self.assertEqual(self.evaluate(context)['decision'], 'DENY')
        context = self.context()
        context['evidence']['jurisdiction_compatibility']['expires_at'] = self.NOW
        self.assertEqual(self.evaluate(context)['decision'], 'DENY')

    def test_revocation_is_independent_of_authentication(self):
        for section in ['session','authorization']:
            context = self.context()
            context[section]['revoked'] = True
            with self.subTest(section=section):
                self.assertEqual(self.evaluate(context)['decision'], 'DENY')
        for name in EXTERNAL_EVIDENCE:
            context = self.context()
            context['evidence'][name]['revoked'] = True
            with self.subTest(evidence=name):
                self.assertEqual(self.evaluate(context)['decision'], 'DENY')

    def test_unknown_missing_and_loosely_typed_fields_deny(self):
        changes = [('session','unknown',True), ('authorization','verified',1), ('session','expires_at',True),
                   ('target','required_scopes',[]), ('policy','allowed_resources','connector:synthetic')]
        for section, field, value in changes:
            context = self.context()
            context[section][field] = value
            with self.subTest(section=section,field=field):
                self.assertEqual(self.evaluate(context)['decision'], 'DENY')
        context = self.context()
        del context['session']['subject']
        self.assertEqual(self.evaluate(context)['decision'], 'DENY')

    def test_input_is_not_mutated_and_invalid_clock_denies(self):
        context = self.context()
        before = copy.deepcopy(context)
        self.evaluate(context)
        self.assertEqual(context, before)
        for clock in [True, 1.0, 'now']:
            self.assertEqual(evaluate_gateway(context, now=clock)['decision'], 'DENY')


if __name__ == '__main__':
    unittest.main()
