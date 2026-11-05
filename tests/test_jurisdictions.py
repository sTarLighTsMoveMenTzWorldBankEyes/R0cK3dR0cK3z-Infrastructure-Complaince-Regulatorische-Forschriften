import unittest
from forina.jurisdictions import resolve_plan

class JurisdictionPlanTests(unittest.TestCase):
    def test_explicit_cross_border_candidate_overlap_does_not_prove_compatibility(self):
        result = resolve_plan({'jurisdictions':['DE','EU','CH'],'sector':'finance','institutional_contexts':['NATO']})
        self.assertEqual(result['jurisdictions'],['CH','DE','EU'])
        self.assertEqual(result['compatibility'],'REQUIRES_REVIEW')
        self.assertFalse(result['legal_compatibility_verified'])
        self.assertFalse(result['access_granted'])
        self.assertEqual(result['network_access'],'NONE')
        assessment = {r['jurisdiction']:r for r in result['assessments']}
        self.assertIn('CH_FINMA',assessment['CH']['regulatory_candidates'])
        self.assertIn('DORA',assessment['EU']['regulatory_candidates'])
        self.assertIn('DORA',assessment['DE']['regulatory_candidates'])

    def test_nato_not_a_country_and_unknown_or_inferred_scope_rejected(self):
        for body in [{'jurisdictions':['NATO']},{'jurisdictions':[]},{'jurisdictions':['XX']},{'jurisdictions':['.de']},{'jurisdictions':['EU'],'institutional_contexts':['UNSUPPORTED']}]:
            with self.subTest(body=body), self.assertRaises(ValueError):
                resolve_plan(body)
