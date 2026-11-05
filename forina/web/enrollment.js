(() => {
  const section = el('section'); section.id = 'enrollment';
  section.append(el('p', 'FTEP · LOKALES TESTPROFIL', 'eyebrow'), el('h2', 'Enrollment als prüfbarer Ablauf.'), el('p', 'Zeitlich begrenzte Test-Challenge, signierter Testnachweis und Widerruf. Die DNS-Antwort wird lokal simuliert; Organisationsidentität, Compliance und Zugangsrechte bleiben ungeprüft.', 'lead'));
  const nav = document.querySelector('nav'); const anchor = el('a', '05 · FTEP-Test'); anchor.href = '#enrollment'; nav.insertBefore(anchor, nav.lastElementChild); nav.lastElementChild.textContent = '06 · Nachweise';
  const form = el('form', undefined, 'panel'); form.id = 'enrollment-form';
  function field(label, id, tag = 'input') { const wrapper = el('label', label); const input = el(tag); input.id = id; input.required = true; wrapper.append(input); form.append(wrapper); return input; }
  const select = field('Erfasste Organisation', 'enrollment-org', 'select');
  const reference = field('Referenz für die lokale Testfreigabe', 'enrollment-reference'); reference.minLength = 8; reference.maxLength = 200; reference.placeholder = 'TEST-FREIGABE-001';
  const ttl = field('Challenge-Laufzeit in Sekunden (60–900)', 'enrollment-ttl'); ttl.type = 'number'; ttl.min = '60'; ttl.max = '900'; ttl.value = '300';
  const consentLabel = el('label', undefined, 'check-label'); const consent = el('input'); consent.type = 'checkbox'; consent.id = 'enrollment-consent'; consent.required = true; consentLabel.append(consent, el('span', 'Ich gebe diese lokale Testsimulation ausdrücklich frei. Dies ist keine Föderationsaufnahme.')); form.append(consentLabel);
  const submit = el('button', 'Test-Challenge erzeugen'); submit.type = 'submit'; form.append(submit);
  const challenge = el('div', undefined, 'panel hidden'); challenge.id = 'enrollment-challenge';
  const list = el('div'); list.id = 'enrollment-list';
  const verifyForm = el('form', undefined, 'panel'); verifyForm.id = 'test-receipt-form';
  const uploadLabel = el('label', 'Signierten FTEP-Testnachweis prüfen'); const upload = el('input'); upload.type = 'file'; upload.id = 'test-receipt-file'; upload.accept = 'application/json,.json'; upload.required = true; uploadLabel.append(upload); const verifyButton = el('button', 'Testsignatur & Status prüfen'); verifyButton.type = 'submit'; const result = el('p', '', 'muted'); result.id = 'test-receipt-result'; result.setAttribute('aria-live','polite'); verifyForm.append(uploadLabel, verifyButton, result);
  const key = el('a', 'Öffentlichen lokalen Testschlüssel herunterladen ↓', 'download secondary'); key.href = '/api/enrollments/test-key'; key.download = 'forina-test-public-key.json';
  section.append(form, challenge, list, verifyForm, el('p', 'Signaturprüfung verwendet ausschließlich den lokal hinterlegten Testschlüssel und den lokalen Widerrufsstand. Ein gültiger Testnachweis verleiht keine Föderationsberechtigung.', 'muted'), key);
  $('evidence').before(section);
  let active = null;
  const states = {CHALLENGE_ISSUED:'Test-Challenge offen', TEST_RECEIPT_ISSUED:'Testnachweis signiert', REVOKED:'Widerrufen', EXPIRED:'Abgelaufen'};
  function statusText(data) { return `Signatur: ${data.signature_valid ? 'gültig' : 'ungültig'} · Laufzeit: ${data.time_valid ? 'gültig' : 'ungültig'} · Vorgang: ${data.status_known ? 'lokal bekannt' : 'unbekannt'} · Widerruf: ${data.revoked ? 'ja' : 'nein'} · Im Test verwendbar: ${data.usable_for_test ? 'ja' : 'nein'} · Föderationszugang: nein`; }
  function setOrganizations(orgs) { const previous = select.value; select.replaceChildren(); for (const org of orgs) { const option = el('option', `${org.name} · ${org.domain}`); option.value = org.id; select.append(option); } if (orgs.some(o => o.id === previous)) select.value = previous; submit.disabled = !orgs.length; }
  async function refresh() {
    const entries = await api('/api/enrollments'); list.replaceChildren();
    for (const entry of entries) {
      const card = el('article', undefined, 'org'); card.append(el('h3', entry.domain), el('span', states[entry.state], 'pill'), el('p', 'TEST ONLY · Identität ungeprüft · Compliance ungeprüft · Nicht in Föderation aufgenommen', 'muted'));
      const actions = el('div', undefined, 'actions');
      if (entry.receipt) {
        const download = el('a', 'Signierten Testnachweis ↓', 'download'); download.href = `/api/enrollments/${entry.id}/receipt`; actions.append(download, action('Testsignatur & Status prüfen', async () => { result.textContent = statusText(await api('/api/enrollments/verify-test-receipt', entry.receipt)); result.scrollIntoView({behavior:'smooth',block:'center'}); }, 'secondary'));
      }
      if (entry.state !== 'REVOKED') actions.append(action('Testvorgang widerrufen', async () => { const reason = prompt('Grund für den lokalen Widerruf:'); if (!reason) return; await api(`/api/enrollments/${entry.id}/revoke`, {reason}); if (active?.id === entry.id) { active = null; challenge.classList.add('hidden'); } await refresh(); notify('Lokaler Testvorgang widerrufen.'); }, 'secondary'));
      card.append(actions); list.append(card);
    }
  }
  document.addEventListener('forina:organizations', event => setOrganizations(event.detail));
  form.onsubmit = async event => {
    event.preventDefault(); submit.disabled = true;
    try {
      active = await api('/api/enrollments', {organization_id:select.value, authorization_reference:reference.value, test_consent:consent.checked, ttl_seconds:Number(ttl.value)});
      const current = active; challenge.replaceChildren(el('h3', 'DNS-Testfixture · nur lokal'), el('p', `Gültig bis ${new Date(current.challenge.expires_at * 1000).toLocaleString('de-DE')}`, 'muted'), el('pre', JSON.stringify({name:current.challenge.dns_name,value:current.challenge.txt_value},null,2)));
      challenge.append(action('Passende DNS-Antwort lokal simulieren', async () => {
        await api(`/api/enrollments/${current.id}/simulate`, {fixture:{name:current.challenge.dns_name,value:current.challenge.txt_value}});
        active = null; challenge.replaceChildren(el('p', 'Simulation abgeschlossen; der signierte Testnachweis steht unten bereit.', 'muted')); await refresh();
      })); challenge.classList.remove('hidden'); await refresh();
    } catch (e) { notify(e.message); } finally { submit.disabled = false; }
  };
  verifyForm.onsubmit = async event => { event.preventDefault(); try { const file = upload.files[0]; if (file.size > 100000) throw new Error('Testnachweis darf höchstens 100 KB groß sein'); result.textContent = statusText(await api('/api/enrollments/verify-test-receipt', JSON.parse(await file.text()))); } catch (e) { notify(e.message); } };
  Promise.all([api('/api/organizations').then(setOrganizations), refresh()]).catch(e => notify('FTEP-Test konnte nicht geladen werden: ' + e.message));
})();
