(() => {
  let rules = [], modules = {}, selected = null, rulePage = 1, sourcePage = 1;
  let preview = null;
  let authoredSource = null;
  const states = {DRAFT:'Entwurf', APPROVED_FOR_PLANNING:'Für Planung freigegeben', REVIEW_OVERDUE:'Wiedervorlage überfällig', REJECTED:'Abgelehnt', RETIRED:'Zurückgezogen'};
  const kinds = {LEGAL_REFERENCE:'Rechtsverweis', STANDARD_REFERENCE:'Standardverweis', REGULATORY_CATALOG_ENTRY:'Importierter Katalogeintrag', INTERNAL_CONTROL:'Interne Vorgabe', SOFTWARE_POLICY:'Software-Policy', USER_AUTHORED_REQUIREMENT:'Fachlich erfasste Anforderung'};
  const path = id => `/api/compliance/rules/${encodeURIComponent(id)}`;
  const lines = id => $(id).value.split('\n').map(x => x.trim()).filter(Boolean);
  const codes = id => $(id).value.split(',').map(x => x.trim()).filter(Boolean);
  const authoredForm = el('form', undefined, 'panel hidden'); authoredForm.id = 'authored-rule-form';
  authoredForm.append(el('h3', 'Anforderung aus einer Quelle erfassen'), el('p', 'Hier kannst du auch Anforderungen zu bisher nicht automatisch erkannten Rechtsakten oder Standards formulieren. Die Zuordnung bleibt eine fachlich zu prüfende Interpretation.', 'muted'), el('p', '', 'muted'));
  const authoredOrigin = authoredForm.lastChild;
  for (const [id, label, tag] of [['authored-title','Anforderungstitel','input'],['authored-requirement','Anforderung','textarea'],['authored-module','Architekturmodul','select']]) {
    const wrapper = el('label', label); const field = el(tag); field.id = id; field.required = true; if (tag !== 'select') field.maxLength = tag === 'input' ? 200 : 2000; wrapper.append(field); authoredForm.append(wrapper);
  }
  const createButton = el('button', 'Als Prüfentwurf anlegen'); createButton.type = 'submit'; authoredForm.append(createButton);
  $('compliance-sources').parentElement.append(authoredForm);
  function openAuthored(document, link) {
    authoredSource = {document_id:document.id || document.document_id, link_id:link?.id || null};
    authoredOrigin.textContent = (document.title || '') + (link ? ' · ' + link.url : '');
    $('authored-title').value = ''; $('authored-requirement').value = '';
    $('authored-module').replaceChildren(); for (const [value, label] of Object.entries(modules)) { const option = el('option', label); option.value = value; $('authored-module').append(option); }
    authoredForm.classList.remove('hidden'); authoredForm.scrollIntoView({behavior:'smooth',block:'center'});
  }
  authoredForm.onsubmit = async event => {
    event.preventDefault(); createButton.disabled = true;
    try {
      const created = await api('/api/compliance/rules', {...authoredSource, title:$('authored-title').value, requirement:$('authored-requirement').value, module:$('authored-module').value});
      authoredForm.classList.add('hidden'); await refresh(); await loadRule(created.id); notify('Quellenbezogener Entwurf angelegt. Kontrollen, Nachweise und Geltungsbereich können jetzt gepflegt werden.');
    } catch(e) { notify(e.message); } finally { createButton.disabled = false; }
  };

  function pages(target, page, total, change) {
    target.replaceChildren(action('← Zurück', () => change(page - 1), 'secondary'), el('span', `${page} / ${total}`, 'muted'), action('Weiter →', () => change(page + 1), 'secondary'));
    target.firstChild.disabled = page <= 1; target.lastChild.disabled = page >= total;
  }
  function renderRules() {
    const query = $('rule-query').value.toLocaleLowerCase();
    const filtered = rules.filter(r => (!query || `${r.code} ${r.title} ${r.requirement}`.toLocaleLowerCase().includes(query)) && (!$('rule-module').value || r.module === $('rule-module').value) && (!$('rule-state').value || r.current_state === $('rule-state').value));
    const count = Math.max(1, Math.ceil(filtered.length / 12)); rulePage = Math.min(count, rulePage);
    $('rule-list').replaceChildren(el('p', `${filtered.length} Anforderungen · Fundstellen sind Quellenbezüge, keine bestätigte Rechtsauslegung`, 'muted'));
    for (const rule of filtered.slice((rulePage - 1) * 12, rulePage * 12)) {
      const card = el('article', undefined, 'rule-card'); const heading = el('div');
      heading.append(el('h3', `${rule.code} · ${rule.title}`), el('p', `${kinds[rule.kind] || rule.kind} · Revision ${rule.revision} · ${modules[rule.module]}`, 'muted'));
      card.append(heading, el('span', states[rule.current_state], 'pill'), el('p', rule.requirement), el('p', `${rule.citation_count} Fundstellen · ${rule.link_count} Quellenlinks`, 'muted'), action('Bearbeiten & Quellen prüfen ↗', () => loadRule(rule.id), 'secondary'));
      $('rule-list').append(card);
    }
    pages($('rule-pages'), rulePage, count, page => { rulePage = page; renderRules(); });
  }
  async function loadSources(page = 1) {
    sourcePage = page;
    const data = await api(`/api/compliance/sources?q=${encodeURIComponent($('source-query').value)}&page=${page}`);
    const panel = $('compliance-sources'); panel.replaceChildren(el('p', `${data.document_total} Dokumente · ${data.link_total} normalisierte Hyperlinks · nicht online geprüft`, 'muted'));
    for (const doc of data.documents) {
      const row = el('details', undefined, 'source-row'); row.append(el('summary', doc.title), el('p', doc.origin, 'muted'), el('code', `SHA-256 ${doc.sha256}`)); if (doc.source_url) row.append(safeLink(doc.source_url, doc.source_url)); row.append(action('Anforderung aus Dokument', () => openAuthored(doc), 'secondary')); panel.append(row);
    }
    for (const link of data.links) {
      const row = el('details', undefined, 'source-row'); const summary = el('summary', link.url); row.append(summary, safeLink(link.url, 'Quelladresse öffnen ↗'), el('p', `${link.citation_count} Fundstellen · Nicht abgerufen. Domainhinweis ist keine Bestätigung des Herausgebers.`, 'muted'));
      for (const c of link.locations) row.append(el('p', `${c.origin} / ${c.title} · ${c.line ? 'Zeile ' + c.line : 'angegebene Quelladresse'}`, 'muted'));
      row.append(action('Anforderung aus Hyperlink', () => openAuthored(link.locations[0], link), 'secondary'));
      panel.append(row);
    }
    pages($('source-pages'), sourcePage, data.pages, loadSources);
  }
  async function refresh() {
    const [summary, list, events] = await Promise.all([api('/api/compliance'), api('/api/compliance/rules'), api('/api/compliance/events')]);
    rules = list; modules = summary.modules;
    $('compliance-stats').replaceChildren();
    for (const [value, title] of [[summary.documents,'Vollständig erfasste Textdateien'],[summary.hyperlinks,'Normalisierte Hyperlinks'],[summary.rules,'Anforderungskandidaten'],[summary.states.APPROVED_FOR_PLANNING || 0,'Aktuell für Planung freigegeben']]) {
      const card = el('div', undefined, 'stat'); card.append(el('strong', value), el('span', title)); $('compliance-stats').append(card);
    }
    $('module-map').replaceChildren();
    for (const [id, label] of Object.entries(modules)) {
      const card = el('div', undefined, 'module-card'); const assigned = rules.filter(r => r.module === id && r.current_state !== 'RETIRED');
      card.append(el('h3', label), el('p', `${assigned.length} zugeordnet · ${assigned.filter(r => r.current_state === 'APPROVED_FOR_PLANNING').length} freigegeben`, 'muted'), action('Anforderungen anzeigen', () => { $('rule-module').value = id; rulePage = 1; renderRules(); }, 'secondary')); $('module-map').append(card);
    }
    if ($('rule-module').options.length === 1) {
      for (const [id, label] of Object.entries(modules)) { const option = el('option', label); option.value = id; $('rule-module').append(option); const target = option.cloneNode(true); $('rule-target').append(target); }
    }
    const archive = summary.packages.find(p => p.id === 'archive-compliance');
    $('package-download').href = `/api/compliance/packages/${archive.id}/${archive.digest}`;
    $('compliance-events').replaceChildren(el('p', 'Lokales Protokoll, nicht manipulationsgeschützt. Namen sind selbst angegeben.', 'muted'));
    for (const e of events) $('compliance-events').append(el('p', `#${e.sequence} · ${new Date(e.at).toLocaleString('de-DE')} · ${e.action} · ${e.rule_id || e.package_id} · ${e.actor}`, 'muted'));
    renderRules();
    await loadSources(sourcePage);
  }
  async function loadRule(id) {
    const data = await api(path(id)); selected = data.rule;
    $('rule-heading').replaceChildren(el('p', `${kinds[selected.kind]} · Revision ${selected.revision} · ${states[selected.current_state]}`, 'eyebrow'), el('h3', selected.title), el('p', 'Modulzuordnung, Kontrollmaßnahmen und Nachweisarten sind Architekturvorschläge zur fachlichen Bearbeitung. Freigabe gilt nur für die lokale Planung.', 'muted'));
    for (const [field, key] of [['rule-title','title'],['rule-requirement','requirement'],['rule-target','module']]) $(field).value = selected[key];
    $('rule-jurisdictions').value = selected.jurisdictions.join(', '); $('rule-sectors').value = selected.sectors.join(', ');
    $('rule-controls').value = selected.controls.join('\n'); $('rule-evidence').value = selected.evidence_requirements.join('\n');
    const citations = $('rule-citations'); citations.replaceChildren(el('h3', `Quellenbezug · ${selected.citations.length} Fundstellen`));
    const docs = Object.fromEntries(data.documents.map(d => [d.id, d]));
    for (const c of selected.citations.slice(0, 30)) {
      const doc = docs[c.document_id]; const row = el('details', undefined, 'source-row'); row.append(el('summary', `${doc?.title || c.document_id} · ${c.pointer === undefined ? (c.line === 0 ? 'Titelverweis' : 'Zeile ' + c.line) : 'JSON-Pfad ' + c.pointer}`), el('p', doc?.origin || '', 'muted'), el('blockquote', c.quote), el('code', `Quell-SHA-256: ${c.source_sha256}`)); citations.append(row);
    }
    if (selected.citations.length > 30) citations.append(el('p', 'Erste 30 Fundstellen angezeigt; vollständige Bezüge sind in der API und im Quellenpaket enthalten.', 'muted'));
    for (const link of data.links.slice(0, 30)) citations.append(safeLink(link.url, link.url));
    if (data.links.length > 30) citations.append(el('p', 'Erste 30 verknüpfte Adressen angezeigt.', 'muted'));
    $('rule-history').replaceChildren();
    for (const revision of [...data.history].reverse()) { const row = el('details', undefined, 'source-row'); row.append(el('summary', `Revision ${revision.revision} · ${states[revision.state]} · ${new Date(revision.updated_utc).toLocaleString('de-DE')}`), el('pre', JSON.stringify(revision, null, 2))); $('rule-history').append(row); }
    $('rule-review').reset();
    $('rule-review').querySelectorAll('button').forEach(b => b.disabled = selected.state !== 'DRAFT');
    $('rule-editor').querySelector('button').disabled = selected.state === 'RETIRED';
    $('rule-detail').classList.remove('hidden'); $('rule-detail').scrollIntoView({behavior:'smooth', block:'start'});
  }
  $('rule-editor').onsubmit = async event => {
    event.preventDefault(); if (!selected) return;
    try {
      const updated = await api(path(selected.id) + '/edit', {expected_revision: selected.revision, title: $('rule-title').value, requirement: $('rule-requirement').value, module: $('rule-target').value, jurisdictions: codes('rule-jurisdictions'), sectors: codes('rule-sectors'), controls: lines('rule-controls'), evidence_requirements: lines('rule-evidence')});
      await refresh(); await loadRule(updated.id); notify('Neue Entwurfsrevision gespeichert. Erneute fachliche Entscheidung erforderlich.');
    } catch (e) { notify(e.message); }
  };
  $('rule-review').onsubmit = async event => {
    event.preventDefault(); if (!selected || !event.submitter) return;
    try {
      // Prevent accidentally approving displayed fields that were not saved yet.
      const dirty = $('rule-title').value !== selected.title || $('rule-requirement').value !== selected.requirement || $('rule-target').value !== selected.module || JSON.stringify(codes('rule-jurisdictions')) !== JSON.stringify(selected.jurisdictions) || JSON.stringify(codes('rule-sectors')) !== JSON.stringify(selected.sectors) || JSON.stringify(lines('rule-controls')) !== JSON.stringify(selected.controls) || JSON.stringify(lines('rule-evidence')) !== JSON.stringify(selected.evidence_requirements);
      if (dirty) throw new Error('Bitte geänderte Anforderungsfelder zuerst als Entwurf speichern.');
      const updated = await api(path(selected.id) + '/review', {expected_revision: selected.revision, decision: event.submitter.value, reviewer: $('reviewer').value, note: $('review-note').value, source_review_reference: $('review-reference').value, review_due: $('review-due').value});
      await refresh(); await loadRule(updated.id); notify('Entscheidung für diese Revision gespeichert.');
    } catch (e) { notify(e.message); }
  };
  $('intake-file').onchange = async () => { try { const file = $('intake-file').files[0]; if (!file) return; if (file.size > 1000000) throw new Error('Textdatei darf höchstens 1 MB groß sein'); $('intake-content').value = await file.text(); $('intake-title').value = file.name; preview = null; $('intake-preview').replaceChildren(); } catch(e) { notify(e.message); } };
  const intakeBody = () => ({title: $('intake-title').value, content: $('intake-content').value, source_url: $('intake-url').value});
  $('intake-form').onsubmit = async event => {
    event.preventDefault();
    try {
      const body = intakeBody(); const result = await api('/api/compliance/preview', body); preview = {body, result};
      const target = $('intake-preview'); target.replaceChildren(el('p', `${result.candidates.length} Prüfkandidaten · ${result.links.length} Hyperlinks · Kein Netzabruf`, 'muted'));
      for (const rule of result.candidates.slice(0,20)) target.append(el('p', `${rule.code} · ${rule.title}`, 'muted'));
      if (!result.candidates.length) target.append(el('p', 'Keine unterstützten Rechtsverweise erkannt. Das Dokument und seine Hyperlinks können dennoch als Quelle eingepflegt werden.', 'muted'));
      target.append(action('Diese Vorschau einpflegen', async () => {
        if (!preview || JSON.stringify(intakeBody()) !== JSON.stringify(preview.body)) throw new Error('Eingabe geändert; Vorschau bitte neu erzeugen.');
        const result = await api('/api/compliance/documents', {...preview.body, preview_digest: preview.result.preview_digest, expected_digest: preview.result.replaces_digest});
        preview = null; await refresh();
        if (selected) await loadRule(selected.id);
        target.replaceChildren(el('p', result.changed ? 'Quelle gespeichert. Betroffene Anforderungen sind Entwürfe und benötigen fachliche Prüfung.' : 'Unveränderte Quelle bereits vorhanden.', 'muted'));
      }));
    } catch (e) { notify(e.message); }
  };
  $('reimport').onclick = async () => { $('reimport').disabled = true; try { const result = await api('/api/compliance/import', {}); await refresh(); if (selected) await loadRule(selected.id); notify(result.changed ? `${result.created_or_revised} Anforderungen neu oder erneut zu prüfen.` : 'Archivbestand unverändert; bestehende Bearbeitungen bleiben erhalten.'); } catch(e) { notify(e.message); } finally { $('reimport').disabled = false; } };
  for (const id of ['rule-query','rule-module','rule-state']) $(id).addEventListener(id === 'rule-query' ? 'input' : 'change', () => { rulePage = 1; renderRules(); });
  $('source-filter').onsubmit = async event => { event.preventDefault(); try { await loadSources(1); } catch(e) { notify(e.message); } };
  refresh().catch(e => notify('Compliance-Einpflege konnte nicht geladen werden: ' + e.message));
})();
