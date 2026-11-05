const $ = (id) => document.getElementById(id);
const el = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; };
let projects = [];
let toastTimer;
function notify(message) { $('toast').textContent = message; $('toast').style.display = 'block'; clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').style.display = 'none', 6500); }
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  const result = await response.json(); if (!response.ok) throw new Error(result.error || 'Anfrage fehlgeschlagen'); return result;
}
function action(label, callback, cls = '') { const b = el('button', label, cls); b.type = 'button'; b.onclick = async () => { b.disabled = true; try { await callback(); } catch (e) { notify(e.message); } finally { b.disabled = false; } }; return b; }
function showJSON(title, data) { const panel = $('plan-panel'); panel.replaceChildren(el('h3', title), el('pre', JSON.stringify(data, null, 2))); panel.classList.remove('hidden'); panel.scrollIntoView({behavior:'smooth', block:'start'}); }
function safeLink(url, label) { try { const u = new URL(url); if (['https:', 'http:'].includes(u.protocol) && !u.username && !u.password) { const a = el('a', label); a.href = u.href; a.target = '_blank'; a.rel = 'noopener noreferrer'; return a; } } catch {} return el('span', label); }
async function showPlan(org) {
  const plan = await api(`/api/organizations/${org.id}/plan`);
  const panel = $('plan-panel'); panel.replaceChildren(el('p', 'PRÜFPLAN · REVIEW REQUIRED', 'eyebrow'), el('h3', org.name), el('p', plan.explanation, 'muted'));
  const compliance = plan.compliance_register;
  panel.append(el('h3', 'Eingepflegte Anforderungen'), el('p', `${compliance.applied_rules.length} für diesen Kontext freigegeben · ${compliance.pending_review.length} Entwürfe oder überfällige Wiedervorlagen im Register. Nachweiserfüllung bleibt ungeprüft.`, 'muted'));
  for (const rule of compliance.applied_rules) { const row = el('div', undefined, 'law'); row.append(el('strong', `${rule.code} · Revision ${rule.revision} · ${rule.title}`), el('p', rule.requirement)); for (const control of rule.controls) row.append(el('p', 'Kontrolle: ' + control)); for (const evidence of rule.evidence_requirements) row.append(el('p', 'Nachweis offen: ' + evidence)); panel.append(row); }
  panel.append(el('h3', 'Weitere Rechtskandidaten aus dem Ausgangskatalog'));
  for (const [code, law] of Object.entries(plan.possible_regulations)) { const row = el('div', undefined, 'law'); row.append(el('strong', `${code} · ${law.title}`), el('p', 'Anwendbarkeit fachlich zu prüfen'), safeLink(law.official_source, 'Quellenverweis öffnen ↗')); panel.append(row); }
  panel.append(el('p', 'Quellenverweise stammen aus dem importierten Katalog und wurden nicht auf Aktualität oder fachliche Passung geprüft.', 'muted'));
  panel.classList.remove('hidden'); panel.scrollIntoView({behavior:'smooth', block:'start'});
}
async function refreshOrganizations() {
  const orgs = await api('/api/organizations'); $('org-list').replaceChildren();
  if (!orgs.length) $('org-list').append(el('div', 'Noch keine Organisation erfasst. Beginne mit einer Domain und dem fachlichen Kontext.', 'panel muted'));
  for (const org of orgs) {
    const card = el('article', undefined, 'org'); card.append(el('h3', org.name), el('p', `${org.domain} · ${org.jurisdictions.join(', ')} · ${org.sector}`), el('p', 'Identität unbestätigt · Domain ungeprüft · Nicht aufgenommen', 'muted'));
    const actions = el('div', undefined, 'actions');
    actions.append(action('Prüfplan', () => showPlan(org)), action('Nachweis erzeugen', async () => { await api('/api/records', {organization_id: org.id}); await refreshRecords(); notify('Unsignierter Prüfentwurf gespeichert.'); }, 'secondary'), action('TXT-Entwurf', async () => {
      const reference = prompt('Freigabereferenz für den Challenge-Entwurf (mindestens 8 Zeichen):'); if (reference === null) return;
      showJSON('DNS-TXT-Entwurf · keine DNS-Änderung', await api(`/api/organizations/${org.id}/challenge`, {authorization_reference: reference}));
    }, 'secondary'));
    card.append(actions); $('org-list').append(card);
  }
  $('stat-orgs').textContent = orgs.length;
  document.dispatchEvent(new CustomEvent('forina:organizations', {detail:orgs}));
}
async function refreshRecords() {
  const records = await api('/api/records'); $('records').replaceChildren();
  if (!records.length) $('records').append(el('p', 'Erzeuge bei einer Organisation einen Nachweis, um das erste Paket zu exportieren.', 'muted'));
  for (const record of records) {
    const card = el('article', undefined, 'record'); card.append(el('h3', record.components.organization.name), el('p', `${new Date(record.created_utc).toLocaleString('de-DE')} · Entwurf · Unsigniert`), el('p', `Bundle SHA-256: ${record.bundle_sha256}`));
    const a = el('a', 'Nachweispaket herunterladen ↓', 'download'); a.href = `/api/records/${record.id}/export`; card.append(a); $('records').append(card);
  }
  $('stat-records').textContent = records.length;
}
async function init() {
  const catalog = await api('/api/catalog'); projects = catalog.projects;
  const stats = [['12', 'Quellarchive', ''], [String(projects.reduce((n,p) => n + p.file_count,0)), 'Originaldateien', ''], ['0', 'Organisationen', 'stat-orgs'], ['0', 'Nachweispakete', 'stat-records']];
  for (const [value, label, id] of stats) { const card = el('div', undefined, 'stat'); const strong = el('strong', value); if (id) strong.id = id; card.append(strong, el('span', label)); $('stats').append(card); }
  $('source-count').textContent = `${projects.length} ARCHIVE`;
  for (const p of projects) { const card = el('article', undefined, 'card'); card.append(el('p', p.role.toUpperCase(), 'eyebrow'), el('h3', p.archive.replace(/\.zip$/, '')), el('p', p.description), el('p', `${p.file_count} Dateien · ${p.integration === 'Guardrails adapter' ? 'Prüfplan-Adapter integriert' : 'Als Quelle erschlossen'}`)); const details = el('details'); details.append(el('summary','Herkunft & Integrität'), el('code',`Archiv SHA-256: ${p.archive_sha256}`), el('p', 'Archivinhalt ist keine extern bestätigte Aussage.')); card.append(details); $('projects').append(card); }
  for (const code of Object.keys(catalog.jurisdictions)) { const option = el('option', code); option.value = code; option.selected = code === 'EU'; $('jurisdictions').append(option); }
  await refreshOrganizations(); await refreshRecords();
}
$('search-form').onsubmit = async (event) => { event.preventDefault(); try { const result = await api(`/api/search?q=${encodeURIComponent($('query').value)}`); $('search-results').replaceChildren(el('p', `${result.total} Treffer · maximal 60 angezeigt · Suche in Textauszügen`, 'muted')); for (const hit of result.results) { const row = el('article', undefined, 'result'); const project = projects.find(p => p.id === hit.project_id); row.append(el('strong', project?.role || 'Quelle'), el('p', hit.path), el('p', hit.excerpt)); $('search-results').append(row); } } catch(e) { notify(e.message); } };
$('org-form').onsubmit = async (event) => { event.preventDefault(); const button = event.target.querySelector('button'); button.disabled = true; try { const data = Object.fromEntries(new FormData(event.target)); data.jurisdictions = [...$('jurisdictions').selectedOptions].map(o => o.value); await api('/api/organizations', data); event.target.reset(); for (const o of $('jurisdictions').options) o.selected = o.value === 'EU'; await refreshOrganizations(); notify('Organisation lokal erfasst. Prüfstatus: unbestätigt.'); } catch(e) { notify(e.message); } finally { button.disabled = false; } };
$('verify-form').onsubmit = async (event) => { event.preventDefault(); try { const file = $('verify-file').files[0]; if (file.size > 5000000) throw new Error('Datei größer als 5 MB'); const result = await api('/api/verify', JSON.parse(await file.text())); $('verify-result').textContent = result.consistent ? 'Komponenten und Bundle-Hash sind konsistent. Keine Signatur oder Herkunftsbestätigung.' : 'Hash-Abweichung: Das Paket ist inkonsistent.'; } catch(e) { notify(e.message); } };
init().catch(e => notify(`Arbeitsraum konnte nicht geladen werden: ${e.message}`));
