"""Optional UI smoke test. Requires installed Playwright and Chromium, not app dependencies."""
import datetime as dt
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]

def run():
    with tempfile.TemporaryDirectory() as storage:
        process = subprocess.Popen([sys.executable, '-m', 'forina.server', '--port', '0', '--storage', storage], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            line = process.stdout.readline()
            if 'loopback port' not in line:
                raise RuntimeError('Testserver konnte nicht starten')
            base = 'http://127.0.0.1:' + line.strip().split()[-1]
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=shutil.which('chromium'), headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
                context = browser.new_context(viewport={'width':1440, 'height':1000}, accept_downloads=True)
                context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(base + '/') else route.abort())
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('response', lambda response: print('HTTP error:', response.status, response.url, response.text()) if response.status >= 400 else None)
                page.goto(base, wait_until='networkidle')
                expect(page.locator('#compliance-stats')).to_contain_text('90')
                page.locator('a[href="#compliance"]').click()
                page.get_by_text('Weitere Dokumente und Hyperlinks einpflegen', exact=True).click()
                page.locator('#intake-title').fill('Browser compliance fixture.md')
                page.locator('#intake-url').fill('https://eur-lex.europa.eu/eli/reg/2016/679/oj')
                page.locator('#intake-content').fill('DSGVO Artikel 5: synthetischer Prüffall. https://eur-lex.europa.eu/eli/reg/2016/679/oj')
                page.locator('#intake-form button').click()
                expect(page.locator('#intake-preview')).to_contain_text('1 Prüfkandidaten')
                page.get_by_role('button', name='Diese Vorschau einpflegen', exact=True).click()
                expect(page.locator('#intake-preview')).to_contain_text('Quelle gespeichert')
                page.locator('#rule-query').fill('GDPR')
                card = page.locator('.rule-card').filter(has=page.get_by_role('heading', name='GDPR · DSGVO / GDPR', exact=True))
                card.get_by_role('button').click()
                expect(page.locator('#rule-heading')).to_contain_text('Revision 2')
                page.locator('#rule-jurisdictions').fill('EU')
                page.locator('#rule-sectors').fill('finance')
                page.locator('#rule-editor button').click()
                if not page.locator('#rule-editor').evaluate('(form) => form.checkValidity()'):
                    raise AssertionError(page.locator('#rule-editor').evaluate('(form) => [...form.elements].filter(e => e.validity && !e.validity.valid).map(e => ({id:e.id, value:e.value, message:e.validationMessage}))'))
                expect(page.locator('#rule-heading')).to_contain_text('Revision 3')
                page.locator('#reviewer').fill('Synthetic UI reviewer')
                page.locator('#review-note').fill('Synthetic test review for explicitly scoped planning only.')
                page.locator('#review-reference').fill('TEST-UI-001')
                page.locator('#review-due').fill((dt.date.today()+dt.timedelta(days=10)).isoformat())
                page.get_by_role('button', name='Für Planung freigeben', exact=True).click()
                expect(page.locator('#rule-heading')).to_contain_text('Für Planung freigegeben')
                page.locator('#org-form input[name="name"]').fill('Synthetic UI Organization')
                page.locator('#org-form input[name="domain"]').fill('example.org')
                page.locator('#org-form select[name="sector"]').select_option('finance')
                page.locator('#jurisdictions').select_option('EU')
                page.locator('#org-form button').click()
                expect(page.locator('#stat-orgs')).to_have_text('1')
                page.get_by_role('button', name='Prüfplan', exact=True).click()
                expect(page.locator('#plan-panel')).to_contain_text('1 für diesen Kontext freigegeben')
                expect(page.locator('#plan-panel')).to_contain_text('Nachweis offen:')
                page.get_by_role('button', name='Nachweis erzeugen', exact=True).click()
                expect(page.locator('#stat-records')).to_have_text('1')
                with page.expect_download() as pending:
                    page.get_by_role('link', name='Nachweispaket herunterladen ↓', exact=True).click()
                download = pending.value
                with zipfile.ZipFile(download.path()) as archive:
                    raw = archive.read('record.json')
                    snapshot = json.loads(archive.read('compliance_register.json'))
                    assert len(snapshot['applied_rules']) == 1
                    assert snapshot['applied_rules'][0]['revision'] == 4
                page.locator('#verify-file').set_input_files({'name':'record.json', 'mimeType':'application/json', 'buffer':raw})
                page.locator('#verify-form button').click()
                expect(page.locator('#verify-result')).to_contain_text('sind konsistent')
                page.locator('#intake-content').fill('DSGVO Artikel 5: neue Version des synthetischen Prüffalls.')
                page.locator('#intake-form button').click()
                expect(page.locator('#intake-preview')).to_contain_text('1 Prüfkandidaten')
                page.get_by_role('button', name='Diese Vorschau einpflegen', exact=True).click()
                expect(page.locator('#rule-heading')).to_contain_text('Revision 5')
                expect(page.locator('#rule-heading')).to_contain_text('Entwurf')
                expect(page.locator('#compliance-stats')).to_contain_text('0')
                page.get_by_text('Dokumente und Hyperlinks mit Fundstellen', exact=True).click()
                page.locator('#source-query').fill('eur-lex.europa.eu')
                page.locator('#source-filter button').click()
                first_link = page.locator('#compliance-sources .source-row').first
                expect(first_link).to_contain_text('eur-lex.europa.eu')
                first_link.locator('summary').click()
                first_link.get_by_role('button', name='Anforderung aus Hyperlink', exact=True).click()
                page.locator('#authored-title').fill('Synthetic custom requirement')
                page.locator('#authored-requirement').fill('Review a new source-based architecture requirement.')
                page.locator('#authored-module').select_option('governance_review')
                page.locator('#authored-rule-form button').click()
                expect(page.locator('#rule-heading')).to_contain_text('Synthetic custom requirement')
                expect(page.locator('#rule-heading')).to_contain_text('Entwurf')
                page.locator('#enrollment-reference').fill('SYNTHETIC-UI-CONSENT')
                page.locator('#enrollment-consent').check()
                page.locator('#enrollment-form button').click()
                expect(page.locator('#enrollment-challenge')).to_contain_text('_forina-test-challenge.example.org')
                page.get_by_role('button', name='Passende DNS-Antwort lokal simulieren', exact=True).click()
                expect(page.locator('#enrollment-list')).to_contain_text('Testnachweis signiert')
                with page.expect_download() as receipt_pending:
                    page.get_by_role('link', name='Signierten Testnachweis ↓', exact=True).click()
                receipt_bytes = Path(receipt_pending.value.path()).read_bytes()
                test_receipt = json.loads(receipt_bytes)
                assert test_receipt['payload']['access_granted'] is False
                page.locator('#test-receipt-file').set_input_files({'name':'ftep-test.json','mimeType':'application/json','buffer':receipt_bytes})
                page.locator('#test-receipt-form button').click()
                expect(page.locator('#test-receipt-result')).to_contain_text('Im Test verwendbar: ja')
                page.once('dialog', lambda dialog: dialog.accept('SYNTHETIC-UI-REVOCATION'))
                page.get_by_role('button', name='Testvorgang widerrufen', exact=True).click()
                expect(page.locator('#enrollment-list')).to_contain_text('Widerrufen')
                page.locator('#test-receipt-form button').click()
                expect(page.locator('#test-receipt-result')).to_contain_text('Signatur: gültig')
                expect(page.locator('#test-receipt-result')).to_contain_text('Im Test verwendbar: nein')
                page.locator('#registry-file').set_input_files(str(ROOT/'examples/domain-registry-synthetic.csv'))
                page.locator('#registry-import button').click()
                expect(page.locator('#registry-import-result')).to_contain_text('7 Zeilen · 6 neue URLs · 1 Duplikate')
                expect(page.locator('#registry-stats')).to_contain_text('6')
                expect(page.locator('#registry-entries')).to_contain_text('DISCOVERED')
                page.locator('#registry-mode').select_option('domains')
                page.locator('#registry-filter button').click()
                expect(page.locator('#registry-entries')).to_contain_text('1 unterschiedliche URLs')
                with page.expect_download() as master_pending:
                    page.get_by_role('link',name='Master Registry als CSV herunterladen ↓',exact=True).click()
                master_csv = Path(master_pending.value.path()).read_text()
                assert 'NOT_SIGNED' in master_csv and 'DISCOVERED' in master_csv
                page.locator('#resolver-codes').fill('EU, DE, CH')
                page.locator('#resolver-sector').select_option('finance')
                page.locator('#jurisdiction-plan-form button').click()
                expect(page.locator('#jurisdiction-plan-result')).to_contain_text('Kompatibilität: fachlich zu prüfen')
                expect(page.locator('#jurisdiction-plan-result')).to_contain_text('CH_FINMA')
                page.locator('#rule-detail').scroll_into_view_if_needed()
                output = ROOT / '.runtime'
                output.mkdir(exist_ok=True)
                page.screenshot(path=str(output / 'compliance-desktop.png'))
                page.set_viewport_size({'width':390, 'height':844})
                page.locator('a[href="#compliance"]').click()
                page.screenshot(path=str(output / 'compliance-mobile.png'))
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile horizontal overflow'
                assert not errors, errors
                browser.close()
                print('UI smoke passed: compliance, FTEP, CSV import/dedup/export, explicit jurisdiction plan, mobile layout; no JS errors.')
        finally:
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()

if __name__ == '__main__':
    run()
