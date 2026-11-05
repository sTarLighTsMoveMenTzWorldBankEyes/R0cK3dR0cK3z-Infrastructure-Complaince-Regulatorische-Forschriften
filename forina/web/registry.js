(() => {
  const section = el('section'); section.id = 'master-registry';
  section.append(el('p','CSV → DOMAIN & COMPLIANCE MASTER REGISTRY','eyebrow'),el('h2','Viele URLs. Ein geordneter Prüfbestand.'),el('p','Bis zu 72.000 CSV-Zeilen offline einpflegen, URLs normalisieren und gemeinsame Domains bündeln. Länder- und Institutionstypen sind Hinweise; Prüfungen und Teilnahmefreigaben stehen danach weiterhin aus.','lead'));
  const stats = el('div',undefined,'stats'); stats.id = 'registry-stats'; section.append(stats);
  const form = el('form',undefined,'panel'); form.id = 'registry-import';
  const fileLabel = el('label','CSV-Datei · UTF-8 · maximal 32 MiB'); const file = el('input'); file.id = 'registry-file'; file.type = 'file'; file.accept = '.csv,text/csv'; file.required = true; fileLabel.append(file);
  const columnLabel = el('label','URL-Spaltenname (optional; sonst automatisch erkennen)'); const column = el('input'); column.id = 'registry-column'; column.maxLength = 200; column.placeholder = 'z. B. Website'; columnLabel.append(column);
  const importButton = el('button','CSV offline einpflegen'); importButton.type = 'submit';
  const report = el('div'); report.id = 'registry-import-result'; report.setAttribute('aria-live','polite');
  form.append(fileLabel,columnLabel,importButton,report); section.append(form);
  const download = el('a','Master Registry als CSV herunterladen ↓','download'); download.href = '/api/registry/export.csv';
  const toolbar = el('form',undefined,'toolbar'); toolbar.id = 'registry-filter';
  const queryLabel = el('label','URL oder Domain filtern'); const query = el('input'); query.id = 'registry-query'; query.maxLength = 200; queryLabel.append(query);
  const modeLabel = el('label','Ansicht'); const mode = el('select'); mode.id = 'registry-mode'; for (const [value,label] of [['urls','URLs'],['domains','Domains zusammengefasst']]) { const option = el('option',label); option.value = value; mode.append(option); } modeLabel.append(mode);
  const filterButton = el('button','Anzeigen'); filterButton.type = 'submit'; toolbar.append(queryLabel,modeLabel,filterButton,download);
  const list = el('div'); list.id = 'registry-entries'; const pages = el('div',undefined,'toolbar'); pages.id = 'registry-pages'; section.append(toolbar,list,pages);
  const resolver = el('form',undefined,'panel'); resolver.id = 'jurisdiction-plan-form';
  resolver.append(el('h3','Rechtsraumübergreifende Prüfung vorbereiten'),el('p','Rechtsräume ausdrücklich angeben. Gemeinsame Regelkandidaten bedeuten keine bestätigte rechtliche Kompatibilität. NATO wird als institutioneller Kontext behandelt.','muted'));
  const codesLabel = el('label','Rechtsräume, kommagetrennt'); const codes = el('input'); codes.id = 'resolver-codes'; codes.placeholder = 'DE, CH, EU'; codes.required = true; codesLabel.append(codes);
  const sectorLabel = el('label','Sektor'); const sector = el('select'); sector.id = 'resolver-sector'; for (const [value,label] of [['general','Allgemein'],['finance','Finanzen'],['ai','KI'],['critical','Kritische Infrastruktur'],['crypto','Krypto'],['platform','Plattform'],['government','Verwaltung']]) { const option = el('option',label); option.value = value; sector.append(option); } sectorLabel.append(sector);
  const contextLabel = el('label',undefined,'check-label'); const nato = el('input'); nato.type = 'checkbox'; nato.id = 'resolver-nato'; contextLabel.append(nato,el('span','Institutionellen Kontext NATO gesondert berücksichtigen'));
  const resolveButton = el('button','Prüfbedarf ermitteln'); resolveButton.type = 'submit'; const plan = el('div'); plan.id = 'jurisdiction-plan-result'; plan.setAttribute('aria-live','polite'); resolver.append(codesLabel,sectorLabel,contextLabel,resolveButton,plan); section.append(resolver);
  const gateway = el('div',undefined,'notice'); gateway.id = 'gateway-boundary'; gateway.append(el('strong','Pocket ID · Passkeys · Forward Auth'),el('p','Integrationsvertrag vorbereitet. Ein OIDC-Sessionverifier und ein produktives Gateway sind hier noch nicht eingerichtet. Die Forward-Auth-Schnittstelle verweigert Zugriffe. Auth-Discovery und technische Domainprüfungen wurden nicht ausgeführt.','muted')); section.append(gateway);
  $('sources').before(section);
  const nav = document.querySelector('nav'); const anchor = el('a','CSV Master Registry'); anchor.href = '#master-registry'; nav.insertBefore(anchor,nav.children[1]); [...nav.children].forEach((link,index) => link.textContent = `${String(index+1).padStart(2,'0')} · ${link.textContent.replace(/^\d+\s*·\s*/,'')}`);
  let pageNumber = 1;
  async function refreshSummary() { const summary = await api('/api/registry'); stats.replaceChildren(); for (const [value,label] of [[summary.urls,'Normalisierte URLs'],[summary.domains,'Unterschiedliche Domains'],[summary.batches,'CSV-Importe'],[0,'Automatisch freigeschaltete Portale']]) { const card = el('div',undefined,'stat'); card.append(el('strong',value),el('span',label)); stats.append(card); } }
  async function loadEntries(page = 1) {
    pageNumber = page; const data = await api(`/api/registry/${mode.value}?q=${encodeURIComponent(query.value)}&page=${page}`);
    list.replaceChildren(el('p',`${data.total} Einträge · nur erfasst, nicht verifiziert`,'muted'));
    for (const entry of data.results) {
      const card = el('article',undefined,'org'); card.append(el('h3',entry.url || entry.domain),el('p',`${entry.jurisdiction_hint || 'Unbekannt'} · ${entry.institution_hint || 'Unbekannt'} · reine Hinweise`,'muted'));
      if (entry.url_count !== undefined) card.append(el('p',`${entry.url_count} unterschiedliche URLs`,'muted'));
      card.append(el('span','DISCOVERED','pill'),el('p','DNS / TLS / Identität / Compliance / Authentifizierung: nicht geprüft · Föderation: nicht autorisiert','muted')); list.append(card);
    }
    pages.replaceChildren(action('← Zurück',() => loadEntries(pageNumber-1),'secondary'),el('span',`${data.page} / ${data.pages}`,'muted'),action('Weiter →',() => loadEntries(pageNumber+1),'secondary')); pages.firstChild.disabled = data.page <= 1; pages.lastChild.disabled = data.page >= data.pages;
  }
  form.onsubmit = async event => {
    event.preventDefault(); importButton.disabled = true; report.replaceChildren(el('p','Import wird lokal verarbeitet …','muted'));
    try {
      const source = file.files[0]; if (!source || source.size > 32*1024*1024) throw new Error('CSV fehlt oder ist größer als 32 MiB');
      const params = new URLSearchParams({filename:source.name}); if (column.value.trim()) params.set('url_column',column.value.trim());
      const response = await fetch('/api/registry/import-csv?' + params, {method:'POST',headers:{'Content-Type':'text/csv; charset=utf-8'},body:source});
      const result = await response.json(); if (!response.ok) throw new Error(result.error || 'CSV-Import fehlgeschlagen');
      report.replaceChildren(el('p',`${result.rows_total} Zeilen · ${result.inserted_urls} neue URLs · ${result.duplicate_rows} Duplikate · ${result.invalid_rows} ungültige Einträge`,'muted'),el('p',`Quelldigest: ${result.source_sha256}`,'muted'));
      for (const error of result.error_samples) report.append(el('p',`Zeile ${error.row}: ${error.reason}`,'muted'));
      await refreshSummary(); await loadEntries(1);
    } catch (e) { report.replaceChildren(el('p',e.message,'muted')); notify(e.message); } finally { importButton.disabled = false; }
  };
  toolbar.onsubmit = async event => { event.preventDefault(); try { await loadEntries(1); } catch(e) { notify(e.message); } };
  resolver.onsubmit = async event => {
    event.preventDefault(); resolveButton.disabled = true;
    try {
      const result = await api('/api/jurisdictions/plan',{jurisdictions:codes.value.split(',').map(c=>c.trim().toUpperCase()).filter(Boolean),sector:sector.value,institutional_contexts:nato.checked?['NATO']:[]});
      plan.replaceChildren(el('h3','Kompatibilität: fachlich zu prüfen'),el('p',result.explanation,'muted'));
      for (const row of result.assessments) { const card = el('div',undefined,'law'); card.append(el('strong',row.name),el('p',Object.keys(row.regulatory_candidates).join(', '))); plan.append(card); }
      for (const check of result.open_checks) plan.append(el('p',check,'muted'));
    } catch(e) { notify(e.message); } finally { resolveButton.disabled = false; }
  };
  Promise.all([refreshSummary(),loadEntries()]).catch(e=>notify('Master Registry konnte nicht geladen werden: '+e.message));
})();
