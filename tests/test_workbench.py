import copy
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
import urllib.error
import urllib.request
import zipfile

from forina.core import Workbench, verify_record
from forina.server import handler

class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workbench = Workbench(self.temp.name)

    def organization(self):
        return self.workbench.add_organization({'name': 'Synthetic Organization', 'domain': 'example.org', 'jurisdictions': ['EU', 'DE', 'US'], 'sector': 'finance'})

    def test_all_sources_and_search_provenance(self):
        projects = self.workbench.projects()
        self.assertEqual(len(projects), 12)
        self.assertEqual(sum(p['file_count'] for p in projects), 503)
        self.assertEqual(len({p['id'] for p in projects}), 12)
        for project in projects:
            self.assertEqual(len(project['archive_sha256']), 64)
        results = self.workbench.search('OPA')
        self.assertGreater(results['total'], 0)
        self.assertTrue(all(len(r['sha256']) == 64 for r in results['results']))

    def test_policy_never_grants_access(self):
        org = self.organization()
        self.assertEqual(org['identity_status'], 'UNVERIFIED')
        plan = self.workbench.plan(org['id'])
        self.assertEqual(plan['decision'], 'REVIEW_REQUIRED')
        self.assertFalse(plan['access_granted'])
        self.assertIn('DORA', plan['possible_regulations'])
        self.assertIn('US_GLBA', plan['possible_regulations'])

    def test_validation_and_persistence(self):
        for patch in [{'domain':'https://user:password@example.org'}, {'domain':'127.0.0.1'}, {'sector':'unknown'}, {'jurisdictions':['XX']}, {'lei':'invalid'}]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                self.workbench.add_organization({'name':'test', 'domain':'example.org', **patch})
        org = self.organization()
        self.assertEqual(Workbench(self.temp.name).organization(org['id']), org)

    def test_challenge_is_pending_not_verification(self):
        org = self.organization()
        challenge = self.workbench.challenge(org['id'], 'SYNTHETIC-REFERENCE-001')
        self.assertFalse(challenge['domain_control_verified'])
        self.assertFalse(challenge['federation_access_granted'])
        self.assertEqual(challenge['txt_name'], '_forina-challenge.example.org')
        self.assertNotEqual(challenge['txt_value'], self.workbench.challenge(org['id'], 'SYNTHETIC-REFERENCE-001')['txt_value'])

    def test_export_integrity_and_tampering(self):
        org = self.organization()
        record = self.workbench.create_record(org['id'])
        self.assertFalse(record['signed'])
        self.assertFalse(record['access_granted'])
        self.assertEqual(len(record['components']['sources']), 12)
        with zipfile.ZipFile(io.BytesIO(self.workbench.export(record['id']))) as archive:
            restored = json.loads(archive.read('record.json'))
            self.assertEqual(json.loads(archive.read('organization.json')), org)
        self.assertTrue(verify_record(restored)['consistent'])
        changed = copy.deepcopy(restored)
        changed['components']['organization']['name'] = 'Tampered'
        self.assertFalse(verify_record(changed)['consistent'])
        self.assertFalse(verify_record(restored)['signature_verified'])

    def test_missing_record_and_malformed_bundle(self):
        with self.assertRaises(KeyError):
            self.workbench.export('missing')
        with self.assertRaises(ValueError):
            verify_record({})

class HttpWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workbench = Workbench(self.temp.name)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler(self.workbench))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.cleanup)
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.client = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def cleanup(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, data=None, headers=None):
        raw = None if data is None else json.dumps(data).encode()
        request = urllib.request.Request(self.base + path, data=raw, headers={'Content-Type':'application/json', **(headers or {})})
        return self.client.open(request, timeout=10)

    def test_complete_http_workflow(self):
        with self.request('/') as response:
            self.assertIn('FORINA'.encode(), response.read())
        with self.request('/api/organizations', {'name':'HTTP Test','domain':'example.org','jurisdictions':['EU'],'sector':'ai'}) as response:
            self.assertEqual(response.status, 201)
            org = json.load(response)
        with self.request('/api/records', {'organization_id':org['id']}) as response:
            record = json.load(response)
        with self.request(f"/api/records/{record['id']}/export") as response:
            self.assertEqual(response.headers['Content-Type'], 'application/zip')
            with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
                self.assertTrue(verify_record(json.loads(archive.read('record.json')))['consistent'])

    def test_reject_cross_origin_unknown_and_bad_input(self):
        for path, data, headers, code in [('/api/organizations',{}, {'Origin':'https://other.example'},403),('/api/organizations',{'name':'no domain'},{},400),('/api/unknown',None,{},404),('/api/health',None,{'Host':'attacker.example'},403)]:
            with self.subTest(path=path,code=code), self.assertRaises(urllib.error.HTTPError) as error:
                self.request(path,data,headers)
            self.assertEqual(error.exception.code, code)

    def test_document_to_review_to_plan_and_export_over_http(self):
        body = {'title':'HTTP document.md','content':'DSGVO Art. 5 https://eur-lex.europa.eu/eli/reg/2016/679/oj'}
        with self.request('/api/compliance/preview', body) as response:
            preview = json.load(response)
        with self.request('/api/compliance/documents', {**body,'preview_digest':preview['preview_digest'],'expected_digest':preview['replaces_digest']}) as response:
            self.assertTrue(json.load(response)['changed'])
        with self.request('/api/compliance/rules/law%3AGDPR') as response:
            rule = json.load(response)['rule']
        with self.request('/api/compliance/rules/law%3AGDPR/edit', {'expected_revision':rule['revision'],'jurisdictions':['EU'],'sectors':['finance']}) as response:
            edited = json.load(response)
        with self.request('/api/compliance/rules/law%3AGDPR/review', {'expected_revision':edited['revision'],'decision':'approve','reviewer':'HTTP Synthetic reviewer','note':'Synthetic scope review','source_review_reference':'TEST-HTTP-001','review_due':(dt.date.today()+dt.timedelta(days=10)).isoformat()}) as response:
            self.assertEqual(json.load(response)['state'], 'APPROVED_FOR_PLANNING')
        with self.assertRaises(urllib.error.HTTPError) as stale:
            self.request('/api/compliance/rules/law%3AGDPR/edit', {'expected_revision':rule['revision'],'jurisdictions':['US']})
        self.assertEqual(stale.exception.code, 409)
        with self.request('/api/organizations', {'name':'Synthetic HTTP finance','domain':'example.org','jurisdictions':['EU'],'sector':'finance'}) as response:
            org = json.load(response)
        with self.request(f"/api/organizations/{org['id']}/plan") as response:
            plan = json.load(response)
        self.assertEqual(len(plan['compliance_register']['applied_rules']), 1)
        self.assertFalse(plan['access_granted'])
        with self.request('/api/records', {'organization_id':org['id']}) as response:
            record = json.load(response)
        with self.request(f"/api/records/{record['id']}/export") as response:
            with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
                self.assertIn('compliance_register.json', archive.namelist())
                self.assertEqual(json.loads(archive.read('compliance_register.json'))['applied_rules'][0]['id'], 'law:GDPR')

    def test_ftep_signed_test_receipt_and_revocation_over_http(self):
        with self.request('/api/organizations', {'name':'Synthetic FTEP HTTP','domain':'example.org'}) as response:
            org = json.load(response)
        with self.request('/api/enrollments', {'organization_id':org['id'],'test_consent':True,'authorization_reference':'SYNTHETIC-HTTP-CONSENT'}) as response:
            self.assertEqual(response.status, 201)
            enrollment = json.load(response)
        with self.request(f"/api/enrollments/{enrollment['id']}/simulate", {'fixture':{'name':enrollment['challenge']['dns_name'],'value':enrollment['challenge']['txt_value']}}) as response:
            issued = json.load(response)
        with self.request(f"/api/enrollments/{enrollment['id']}/receipt") as response:
            self.assertIn('attachment', response.headers['Content-Disposition'])
            receipt = json.load(response)
        self.assertEqual(issued['receipt'], receipt)
        with self.request('/api/enrollments/verify-test-receipt', receipt) as response:
            verified = json.load(response)
        self.assertTrue(verified['usable_for_test'])
        self.assertFalse(verified['access_granted'])
        with self.assertRaises(urllib.error.HTTPError) as replay:
            self.request(f"/api/enrollments/{enrollment['id']}/simulate", {'fixture':{'name':enrollment['challenge']['dns_name'],'value':enrollment['challenge']['txt_value']}})
        self.assertEqual(replay.exception.code, 409)
        with self.request(f"/api/enrollments/{enrollment['id']}/revoke", {'reason':'Synthetic HTTP revocation'}) as response:
            self.assertEqual(json.load(response)['state'], 'REVOKED')
        with self.request('/api/enrollments/verify-test-receipt', receipt) as response:
            verified = json.load(response)
        self.assertTrue(verified['signature_valid'])
        self.assertTrue(verified['revoked'])
        self.assertFalse(verified['usable_for_test'])

    def test_offline_csv_registry_http_import_export_and_no_auth_bypass(self):
        raw = '\ufeffWebsite;Label\nhttps://EXAMPLE.org:443/#fragment;A\nexample.org;Duplicate\nnato.int;Institution\nhttps://u:secret@example.org;Invalid\n'.encode()
        request = urllib.request.Request(self.base+'/api/registry/import-csv?filename=fixture.csv',data=raw,headers={'Content-Type':'text/csv; charset=utf-8'})
        with self.client.open(request,timeout=15) as response:
            self.assertEqual(response.status,201)
            result = json.load(response)
        self.assertEqual(result['rows_total'],4)
        self.assertEqual(result['inserted_urls'],2)
        self.assertEqual(result['duplicate_rows'],1)
        self.assertEqual(result['invalid_rows'],1)
        self.assertEqual(result['source_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertNotIn('secret',json.dumps(result))
        with self.request('/api/registry/urls') as response:
            rows = json.load(response)['results']
        self.assertTrue(all(r['status']=='DISCOVERED' and r['access_granted'] is False and r['jurisdictions']==[] for r in rows))
        with self.request('/api/registry/export.csv') as response:
            self.assertIn('text/csv',response.headers['Content-Type'])
            self.assertIn('NOT_SIGNED',response.read().decode())
        with self.assertRaises(urllib.error.HTTPError) as forward:
            self.request('/api/forward-auth',headers={'Remote-User':'admin','X-Auth-Request-User':'admin'})
        self.assertEqual(forward.exception.code,503)
        with self.request('/api/gateway/plan',{'session':{'verified':True},'access_granted':True}) as response:
            decision = json.load(response)
        self.assertFalse(decision['access_granted'])
        self.assertEqual(decision['decision'],'DENY')
        with self.request('/api/jurisdictions/plan',{'jurisdictions':['EU','CH'],'sector':'finance'}) as response:
            plan = json.load(response)
        self.assertEqual(plan['compatibility'],'REQUIRES_REVIEW')
        self.assertFalse(plan['legal_compatibility_verified'])

if __name__ == '__main__':
    unittest.main()
