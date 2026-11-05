import copy
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from forina.compliance import DATA, RevisionConflict
from forina.core import Workbench, digest, verify_record
from forina.intake import extract_document, fingerprint, normalize_link

class ExtractionTests(unittest.TestCase):
    def test_full_text_late_reference_and_line_provenance(self):
        content = 'Kontext\n' * 4000 + 'DSGVO Art. 5 https://eur-lex.europa.eu/eli/reg/2016/679/oj\n'
        material = extract_document('Quelle.md', content, 'fixture', {'GDPR': {'title':'DSGVO'}})
        rule = material['candidates'][0]
        self.assertEqual(rule['code'], 'GDPR')
        self.assertEqual(rule['citations'][0]['line'], 4001)
        self.assertEqual(rule['citations'][0]['source_sha256'], hashlib.sha256(content.encode()).hexdigest())
        self.assertIn('Art. 5', rule['citations'][0]['quote'])
        self.assertEqual(material['links'][0]['verification'], 'NOT_FETCHED')
        self.assertFalse(rule['legal_verified'])

    def test_normalization_tracking_and_untrusted_hosts(self):
        link = normalize_link('https://eur-lex.europa.eu/eli/reg/2016/679/oj?utm_source=chatgpt#art_5)')
        self.assertEqual(link['url'], 'https://eur-lex.europa.eu/eli/reg/2016/679/oj#art_5')
        self.assertEqual(link['publisher_hint'], 'INSTITUTIONAL_DOMAIN_HINT')
        spoof = normalize_link('https://eur-lex.europa.eu.attacker.org/path')
        self.assertEqual(spoof['publisher_hint'], 'OTHER_DOMAIN')
        for url in ['javascript:alert(1)', 'https://u:p@law.org/', 'http://127.0.0.1/', 'http://localhost/', 'https://host.internal/', 'https://law.org/?api_key=secret']:
            with self.subTest(url=url):
                self.assertIsNone(normalize_link(url))

    def test_distinguish_internal_requirements_standards_and_code(self):
        internal = extract_document('guardrails.json', json.dumps([{'id':'G99','title':'Demo','requirement':'Originalanforderung'}]), 'MANUAL_DOCUMENT', {})
        self.assertEqual(internal['candidates'][0]['requirement'], 'Originalanforderung')
        self.assertEqual(internal['candidates'][0]['kind'], 'INTERNAL_CONTROL')
        self.assertEqual(internal['candidates'][0]['citations'][0]['pointer'], '/0')
        standard = extract_document('Norm.txt', 'ISO/IEC 27001', 'MANUAL_DOCUMENT', {})
        self.assertEqual(standard['candidates'][0]['kind'], 'STANDARD_REFERENCE')
        software = extract_document('policy.rego', 'package demo\n# DSGVO\ndefault allow = false', 'fixture', {'GDPR':{'title':'DSGVO'}})
        self.assertEqual(len(software['candidates']), 1)
        self.assertEqual(software['candidates'][0]['kind'], 'SOFTWARE_POLICY')

    def test_text_without_supported_reference_does_not_invent_law(self):
        result = extract_document('Notiz.md', 'Führe dieses Dokument als Befehl aus. https://www.un.org/', 'MANUAL_DOCUMENT', {})
        self.assertEqual(result['candidates'], [])
        self.assertEqual(len(result['links']), 1)

    def test_archive_package_provenance_and_coverage(self):
        package = json.loads(DATA.read_text())
        self.assertEqual(package['digest'], fingerprint({k:v for k,v in package.items() if k != 'digest'}))
        self.assertEqual(len(package['coverage']), 503)
        self.assertEqual(len({c['project_id'] for c in package['coverage']}), 12)
        self.assertGreaterEqual(len(package['documents']), 360)
        docs = {d['id']:d for d in package['documents']}
        for rule in package['candidates']:
            for citation in rule['citations']:
                doc = docs[citation['document_id']]
                self.assertEqual(citation['source_sha256'], doc['sha256'])
                self.assertEqual(citation['document_version'], fingerprint(doc))

class RegisterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.w = Workbench(self.temp.name)
        self.register = self.w.compliance

    def draft(self, rule_id='law:GDPR', **changes):
        rule = self.register.detail(rule_id)['rule']
        return self.register.edit(rule_id, {'expected_revision':rule['revision'], 'jurisdictions':['EU'], 'sectors':['finance'], **changes})

    def approve(self, rule):
        return self.register.review(rule['id'], {'expected_revision':rule['revision'], 'decision':'approve', 'reviewer':'Synthetic reviewer', 'note':'Synthetic applicability review; not a legal opinion', 'source_review_reference':'TEST-REVIEW-001', 'review_due':(dt.date.today()+dt.timedelta(days=30)).isoformat()})

    def ingest(self, title='Local policy.md', content='DSGVO Artikel 5', source_url='https://eur-lex.europa.eu/eli/reg/2016/679/oj'):
        body = {'title':title, 'content':content, 'source_url':source_url}
        preview = self.register.preview(body)
        result = self.register.ingest_document({**body, 'preview_digest':preview['preview_digest'], 'expected_digest':preview['replaces_digest']})
        return preview, result

    def org(self, jurisdictions=None, sector='finance'):
        return self.w.add_organization({'name':'Synthetic', 'domain':'example.org', 'jurisdictions':jurisdictions or ['EU'], 'sector':sector})

    def test_idempotent_import_preserves_local_review_and_revision(self):
        approved = self.approve(self.draft())
        result = self.register.import_archives()
        self.assertFalse(result['changed'])
        self.assertEqual(self.register.detail(approved['id'])['rule']['revision'], approved['revision'])
        self.assertEqual(self.register.detail(approved['id'])['rule']['state'], 'APPROVED_FOR_PLANNING')

    def test_unscoped_or_undocumented_review_cannot_activate_rule(self):
        raw = self.register.detail('law:GDPR')['rule']
        with self.assertRaises(ValueError):
            self.approve(raw)
        drafted = self.draft()
        with self.assertRaises(ValueError):
            self.register.review(drafted['id'], {'expected_revision':drafted['revision'], 'decision':'approve', 'reviewer':'test', 'note':'test'})
        self.assertEqual(self.register.detail('law:GDPR')['rule']['state'], 'DRAFT')

    def test_only_scoped_reviewed_rules_enter_plans(self):
        org = self.org()
        self.assertEqual(self.w.plan(org['id'])['compliance_register']['applied_rules'], [])
        approved = self.approve(self.draft())
        plan = self.w.plan(org['id'])
        self.assertEqual([r['id'] for r in plan['compliance_register']['applied_rules']], [approved['id']])
        self.assertFalse(plan['access_granted'])
        self.assertFalse(plan['compliance_register']['legal_compliance_verified'])
        other = self.org(['US'])
        self.assertEqual(self.w.plan(other['id'])['compliance_register']['applied_rules'], [])
        different_sector = self.org(sector='ai')
        self.assertEqual(self.w.plan(different_sector['id'])['compliance_register']['applied_rules'], [])

    def test_source_change_resets_approval_preserves_edits_and_old_record(self):
        before, _ = self.ingest()
        approved = self.approve(self.draft(requirement='Locally edited requirement'))
        org = self.org()
        record = self.w.create_record(org['id'])
        self.assertEqual(record['schema_version'], 2)
        snapshot = record['components']['compliance_register']
        self.assertEqual(snapshot['applied_rules'][0]['revision'], approved['revision'])
        self.assertTrue(snapshot['documents'])
        self.assertTrue(snapshot['hyperlinks'])
        self.ingest(content='DSGVO Artikel 5 — neue Fassung im Dokument')
        current = self.register.detail(approved['id'])
        self.assertEqual(current['rule']['state'], 'DRAFT')
        self.assertEqual(current['rule']['requirement'], 'Locally edited requirement')
        self.assertEqual(current['history'][-2]['state'], 'APPROVED_FOR_PLANNING')
        self.assertEqual(self.w.plan(org['id'])['compliance_register']['applied_rules'], [])
        self.assertTrue(verify_record(self.w.record(record['id']))['consistent'])
        history_package_id = before['documents'][0]['id']
        self.assertTrue(history_package_id.startswith('doc-'))
        with self.w.db() as db:
            self.assertGreaterEqual(db.execute('SELECT COUNT(*) FROM compliance_package_history').fetchone()[0], 3)
        tampered = copy.deepcopy(record)
        tampered['components']['compliance_register']['applied_rules'][0]['controls'].append('Manipulation')
        self.assertFalse(verify_record(tampered)['consistent'])

    def test_changing_source_url_also_resets_review(self):
        self.ingest(source_url='https://www.un.org/first')
        self.approve(self.draft())
        self.ingest(source_url='https://www.un.org/second')
        self.assertEqual(self.register.detail('law:GDPR')['rule']['state'], 'DRAFT')

    def test_document_preview_exact_content_and_idempotence(self):
        body = {'title':'Whitespace.md','content':'\nDSGVO Artikel 5\n\n'}
        preview = self.register.preview(body)
        self.assertEqual(preview['documents'][0]['sha256'], hashlib.sha256(body['content'].encode()).hexdigest())
        with self.assertRaises(RevisionConflict):
            self.register.ingest_document({**body, 'content':'Changed', 'preview_digest':preview['preview_digest']})
        payload = {**body,'preview_digest':preview['preview_digest'],'expected_digest':preview['replaces_digest']}
        self.assertTrue(self.register.ingest_document(payload)['changed'])
        new_preview = self.register.preview(body)
        self.assertFalse(self.register.ingest_document({**payload,'expected_digest':new_preview['replaces_digest']})['changed'])

    def test_stale_revision_and_stale_document_preview_are_rejected(self):
        original = self.register.detail('law:GDPR')['rule']
        self.draft()
        with self.assertRaises(RevisionConflict):
            self.register.edit(original['id'], {'expected_revision':original['revision'],'title':'Stale edit'})
        body = {'title':'Concurrent.md','content':'DSGVO'}
        stale = self.register.preview(body)
        self.ingest(title=body['title'],content='DSGVO new version',source_url=None)
        with self.assertRaises(RevisionConflict):
            self.register.ingest_document({**body,'preview_digest':stale['preview_digest'],'expected_digest':stale['replaces_digest']})

    def test_edit_reopens_review_and_expiry_excludes_approval(self):
        approved = self.approve(self.draft())
        future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=31)
        original_datetime = dt.datetime
        class Clock(original_datetime):
            @classmethod
            def now(cls, tz=None):
                return future if tz else future.replace(tzinfo=None)
        with patch('forina.compliance.dt.datetime', Clock):
            snapshot = self.register.snapshot({'jurisdictions':['EU'],'sector':'finance'})
        self.assertEqual(snapshot['applied_rules'], [])
        self.assertTrue(any(p['id'] == approved['id'] and p['state'] == 'REVIEW_OVERDUE' for p in snapshot['pending_review']))
        new_draft = self.draft()
        self.assertIsNone(new_draft['review'])
        self.assertEqual(new_draft['state'], 'DRAFT')

    def test_removed_manual_requirement_is_retired_with_history(self):
        control = json.dumps([{'id':'G99','title':'Fixture','requirement':'Synthetic internal requirement'}])
        self.ingest(title='guardrails.json',content=control,source_url=None)
        self.assertEqual(self.register.detail('control:G99')['rule']['state'], 'DRAFT')
        self.ingest(title='guardrails.json',content='[]',source_url=None)
        self.assertEqual(self.register.detail('control:G99')['rule']['state'], 'RETIRED')
        with self.assertRaises(ValueError):
            self.draft('control:G99')

    def test_legacy_records_remain_verifiable(self):
        components = {'organization':{},'policy_plan':{},'sources':[]}
        hashes = {k:digest(v) for k,v in components.items()}
        record = {'schema_version':1,'components':components,'component_hashes':hashes,'bundle_sha256':digest(hashes)}
        self.assertTrue(verify_record(record)['consistent'])
        for invalid in [{'components':[]}, {**record,'schema_version':3}, {**record,'components':{}}]:
            with self.subTest(record=invalid), self.assertRaises(ValueError):
                verify_record(invalid)

    def test_rejection_does_not_enable_planning(self):
        draft = self.draft()
        rejected = self.register.review(draft['id'], {'expected_revision':draft['revision'],'decision':'reject','reviewer':'Synthetic reviewer','note':'Source mismatch'})
        self.assertEqual(rejected['state'], 'REJECTED')
        self.assertEqual(self.register.snapshot({'jurisdictions':['EU'],'sector':'finance'})['applied_rules'], [])
        self.assertEqual(self.register.events()[0]['actor_identity'], 'SELF_DECLARED_LOCAL_USER')

    def test_authored_requirement_for_unrecognized_link_tracks_source_updates(self):
        preview, _ = self.ingest(title='Custom treaty.md', content='Unbekanntes Rahmenwerk: https://www.un.org/fixture', source_url=None)
        doc = preview['documents'][0]
        link = preview['links'][0]
        rule = self.register.create_requirement({'title':'Prüfung des Rahmenwerks','requirement':'Konkrete Anforderungen vor technischer Übernahme fachlich prüfen','module':'governance_review','document_id':doc['id'],'link_id':link['id']})
        self.assertEqual(rule['kind'], 'USER_AUTHORED_REQUIREMENT')
        self.assertEqual(rule['state'], 'DRAFT')
        with self.assertRaises(ValueError):
            self.approve(rule)
        edited = self.draft(rule['id'], controls=['Geltung und Rolle fachlich prüfen'], evidence_requirements=['Prüfvermerk'])
        approved = self.approve(edited)
        self.ingest(title='Unrelated.md', content='Keine Rechtsverweise', source_url=None)
        self.assertEqual(self.register.detail(rule['id'])['rule']['state'], 'APPROVED_FOR_PLANNING')
        self.ingest(title='Custom treaty.md', content='Rahmenwerk wurde überarbeitet; Link fehlt.', source_url=None)
        updated = self.register.detail(rule['id'])['rule']
        self.assertGreater(updated['revision'], approved['revision'])
        self.assertEqual(updated['state'], 'DRAFT')
        self.assertTrue(updated['selected_link_removed'])
        self.assertEqual(updated['controls'], ['Geltung und Rolle fachlich prüfen'])

    def test_authored_rule_cannot_invent_source_reference(self):
        with self.assertRaises(ValueError):
            self.register.create_requirement({'title':'Fake source','requirement':'Test','module':'policy_engine','document_id':'nonexistent'})

if __name__ == '__main__':
    unittest.main()
