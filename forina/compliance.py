"""Local, versioned compliance intake and human-reviewed planning register."""
import datetime as dt
import json
import uuid
from pathlib import Path

from .intake import MODULES, SECTORS, encoded, extract_document, fingerprint, merge_materials

DATA = Path(__file__).resolve().parent / 'data/compliance.json'
VENDOR = Path(__file__).resolve().parent / 'vendor/guardrails'
EDITABLE = {'title', 'requirement', 'module', 'controls', 'evidence_requirements', 'jurisdictions', 'sectors'}

class RevisionConflict(ValueError):
    pass

def timestamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def required(value, name, limit=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'{name}: nichtleerer Text bis {limit} Zeichen erforderlich')
    return value.strip()

def rows(db):
    return [json.loads(r[0]) for r in db.execute('SELECT r.data FROM compliance_revisions r JOIN (SELECT rule_id, MAX(revision) rev FROM compliance_revisions GROUP BY rule_id) latest ON r.rule_id=latest.rule_id AND r.revision=latest.rev ORDER BY r.rule_id')]

def current(db, rule_id):
    row = db.execute('SELECT data FROM compliance_revisions WHERE rule_id=? ORDER BY revision DESC LIMIT 1', (rule_id,)).fetchone()
    if row is None:
        raise KeyError('Compliance-Anforderung nicht gefunden')
    return json.loads(row[0])

def current_state(rule):
    if rule['state'] == 'APPROVED_FOR_PLANNING' and rule['review']['review_due'] < dt.datetime.now(dt.timezone.utc).date().isoformat():
        return 'REVIEW_OVERDUE'
    return rule['state']

def merge_packages(packages):
    materials = []
    for package in packages:
        materials.extend({'document': d, 'links': [], 'candidates': []} for d in package['documents'])
        if package['documents']:
            materials.append({'document': package['documents'][0], 'links': package['links'], 'candidates': package['candidates']})
    combined = merge_materials(materials)
    for item in combined['candidates']:
        item['citations'].sort(key=encoded)
    for link in combined['links']:
        link['citations'].sort(key=encoded)
    return combined

class ComplianceRegister:
    def __init__(self, connect):
        self.connect = connect
        with connect() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS compliance_packages (id TEXT PRIMARY KEY, data TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS compliance_package_history (id TEXT, digest TEXT, data TEXT NOT NULL, PRIMARY KEY(id, digest));
              CREATE TABLE IF NOT EXISTS compliance_revisions (rule_id TEXT, revision INTEGER, data TEXT NOT NULL, PRIMARY KEY(rule_id, revision));
              CREATE TABLE IF NOT EXISTS compliance_events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS compliance_authored (id TEXT PRIMARY KEY, data TEXT NOT NULL);
            ''')
            for package in self._packages(db):
                db.execute('INSERT OR IGNORE INTO compliance_package_history VALUES (?,?,?)', (package['id'], package['digest'], encoded(package).decode()))
            exists = db.execute('SELECT 1 FROM compliance_packages WHERE id=?', ('archive-compliance',)).fetchone()
        if not exists:
            self.import_archives()

    def _event(self, db, event):
        event = {'at': timestamp(), **event, 'actor_identity': 'SELF_DECLARED_LOCAL_USER'}
        db.execute('INSERT INTO compliance_events(data) VALUES (?)', (encoded(event).decode(),))

    def _append(self, db, rule, prior, action, actor='Local intake'):
        rule = {**rule, 'revision': prior['revision'] + 1 if prior else 1, 'updated_utc': timestamp()}
        db.execute('INSERT INTO compliance_revisions VALUES (?,?,?)', (rule['id'], rule['revision'], encoded(rule).decode()))
        self._event(db, {'action': action, 'rule_id': rule['id'], 'revision': rule['revision'], 'actor': actor})
        return rule

    def _packages(self, db):
        return [json.loads(r[0]) for r in db.execute('SELECT data FROM compliance_packages ORDER BY id')]

    def import_archives(self):
        package = json.loads(DATA.read_text())
        return self._import(package, expected=None, check_expected=False)

    def _import(self, package, expected, check_expected=True):
        if package.get('digest') != fingerprint({k: v for k, v in package.items() if k != 'digest'}):
            raise ValueError('Importpaket hat einen inkonsistenten Hash')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT data FROM compliance_packages WHERE id=?', (package['id'],)).fetchone()
            old_digest = json.loads(old[0])['digest'] if old else None
            if check_expected and old_digest != expected:
                raise RevisionConflict('Dokument wurde inzwischen geändert; Vorschau neu erzeugen')
            if old_digest == package['digest']:
                return {'changed': False, 'created_or_revised': 0, 'package_digest': old_digest}
            db.execute('INSERT OR REPLACE INTO compliance_packages VALUES (?,?)', (package['id'], encoded(package).decode()))
            db.execute('INSERT OR IGNORE INTO compliance_package_history VALUES (?,?,?)', (package['id'], package['digest'], encoded(package).decode()))
            combined = merge_packages(self._packages(db))
            for row in db.execute('SELECT data FROM compliance_authored ORDER BY id'):
                authored = self._authored(json.loads(row[0]), combined)
                if authored:
                    combined['candidates'].append(authored)
            existing = {r['id']: r for r in rows(db)}
            incoming = set()
            changed = 0
            for candidate in combined['candidates']:
                rid = candidate['id']
                incoming.add(rid)
                prior = existing.get(rid)
                source_digest = fingerprint(candidate)
                if prior and prior['input_fingerprint'] == source_digest and prior['state'] != 'RETIRED':
                    continue
                rule = {**candidate, 'input_fingerprint': source_digest, 'state': 'DRAFT', 'review': None, 'edited': False}
                if prior and prior.get('edited'):
                    rule.update({k: prior[k] for k in EDITABLE})
                    rule['edited'] = True
                self._append(db, rule, prior, 'SOURCE_IMPORTED' if prior is None else 'SOURCE_CHANGED_REVIEW_RESET')
                changed += 1
            for rid, prior in existing.items():
                if rid not in incoming and prior['state'] != 'RETIRED':
                    self._append(db, {**prior, 'state': 'RETIRED', 'review': None}, prior, 'SOURCE_REMOVED')
                    changed += 1
            self._event(db, {'action': 'PACKAGE_IMPORTED', 'package_id': package['id'], 'digest': package['digest'], 'actor': 'Local intake', 'rules_changed': changed})
        return {'changed': True, 'created_or_revised': changed, 'package_digest': package['digest']}

    def _authored(self, template, combined):
        document = next((d for d in combined['documents'] if d['id'] == template['document_id']), None)
        if document is None:
            return None
        link = next((l for l in combined['links'] if l['id'] == template.get('link_id') and any(c['document_id'] == document['id'] for c in l['citations'])), None)
        location = next((c for c in link['citations'] if c['document_id'] == document['id']), {}) if link else {}
        citation = {'document_id': document['id'], 'source_sha256': document['sha256'], 'document_version': fingerprint(document),
            'line': location.get('line', 0), 'quote': link['url'] if link else document['title'],
            'relation': 'USER_SELECTED_LINK_NOT_RETRIEVED' if link else 'USER_SELECTED_DOCUMENT_NOT_LEGAL_PROOF'}
        return {k: v for k, v in template.items() if k not in {'document_id', 'link_id'}} | {
            'citations': [citation], 'link_ids': [link['id']] if link else [],
            'selected_link_removed': bool(template.get('link_id') and link is None)}

    def create_requirement(self, body):
        title = required(body.get('title'), 'Anforderungstitel', 200)
        requirement = required(body.get('requirement'), 'Anforderung')
        module = body.get('module')
        if module not in MODULES:
            raise ValueError('Unbekanntes Architekturmodul')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            combined = merge_packages(self._packages(db))
            document_id = required(body.get('document_id'), 'Quellendokument', 100)
            if not any(d['id'] == document_id for d in combined['documents']):
                raise ValueError('Quellendokument ist nicht im Register')
            link_id = body.get('link_id')
            if link_id and not any(l['id'] == link_id and any(c['document_id'] == document_id for c in l['citations']) for l in combined['links']):
                raise ValueError('Hyperlink ist dem Quellendokument nicht zugeordnet')
            rid = 'custom:' + str(uuid.uuid4())
            template = {'id': rid, 'code': 'CUSTOM_' + rid[-8:].upper(), 'kind': 'USER_AUTHORED_REQUIREMENT',
                'title': title, 'requirement': requirement, 'module': module, 'document_id': document_id, 'link_id': link_id,
                'controls': [], 'evidence_requirements': [],
                'jurisdictions': [], 'sectors': [], 'mapping_basis': 'USER_INTERPRETATION_REQUIRES_REVIEW', 'legal_verified': False}
            db.execute('INSERT INTO compliance_authored VALUES (?,?)', (rid, encoded(template).decode()))
            candidate = self._authored(template, combined)
            return self._append(db, {**candidate, 'input_fingerprint': fingerprint(candidate), 'state':'DRAFT', 'review':None, 'edited':True}, None, 'USER_REQUIREMENT_CREATED')

    def _manual_package(self, body):
        title = required(body.get('title'), 'Dokumenttitel', 200)
        required(body.get('content'), 'Dokumentinhalt', 1_000_000)
        content = body['content']
        url = body.get('source_url') or None
        if url is not None:
            url = required(url, 'Quell-URL', 2000)
        definitions = json.loads((VENDOR / 'laws.json').read_text())
        material = extract_document(title, content, 'MANUAL_DOCUMENT', definitions, source_url=url)
        package = {'id': 'manual-' + fingerprint(title)[:24], 'schema_version': 1, **merge_materials([material]), 'coverage': [], 'network_access': 'NONE', 'legal_verification': 'NOT_PERFORMED'}
        package['digest'] = fingerprint(package)
        return package

    def preview(self, body):
        package = self._manual_package(body)
        with self.connect() as db:
            old = db.execute('SELECT data FROM compliance_packages WHERE id=?', (package['id'],)).fetchone()
        return {'preview_digest': package['digest'], 'replaces_digest': json.loads(old[0])['digest'] if old else None,
            'documents': package['documents'], 'links': package['links'], 'candidates': package['candidates'], 'network_access': 'NONE'}

    def ingest_document(self, body):
        package = self._manual_package(body)
        if body.get('preview_digest') != package['digest']:
            raise RevisionConflict('Inhalt und Vorschau stimmen nicht überein; Vorschau neu erzeugen')
        return self._import(package, body.get('expected_digest'))

    def summary(self):
        with self.connect() as db:
            packages = self._packages(db)
            rules = rows(db)
        combined = merge_packages(packages)
        statuses = {}
        for rule in rules:
            state = current_state(rule)
            statuses[state] = statuses.get(state, 0) + 1
        coverage = [c for p in packages for c in p.get('coverage', [])]
        return {'documents': len(combined['documents']), 'hyperlinks': len(combined['links']), 'rules': len(rules), 'states': statuses,
            'files_accounted_for': len(coverage), 'full_text_files': sum(c['status'] == 'FULL_TEXT_EXTRACTED' for c in coverage),
            'uninterpreted_files': sum(c['status'] != 'FULL_TEXT_EXTRACTED' for c in coverage),
            'packages': [{'id': p['id'], 'digest': p['digest']} for p in packages], 'modules': MODULES,
            'network_access': 'NONE', 'legal_verification': 'NOT_PERFORMED'}

    def sources(self, query='', page=1):
        if not isinstance(query, str) or len(query) > 200 or page < 1:
            raise ValueError('Ungültiger Quellenfilter')
        with self.connect() as db:
            combined = merge_packages(self._packages(db))
        query = query.casefold()
        docs = [d for d in combined['documents'] if query in (d['title'] + ' ' + d['origin']).casefold()]
        links = [l for l in combined['links'] if query in l['url'].casefold()]
        offset = (page - 1) * 25
        lookup = {d['id']: d for d in combined['documents']}
        page_links = [{**link, 'locations': [{'title': lookup[c['document_id']]['title'], 'origin': lookup[c['document_id']]['origin'], **c} for c in link['citations'][:5]], 'citation_count': len(link['citations'])} for link in links[offset:offset+25]]
        return {'documents': docs[offset:offset+25], 'links': page_links, 'document_total': len(docs), 'link_total': len(links), 'page': page,
                'pages': max(1, (max(len(docs), len(links)) + 24) // 25)}

    def rules(self):
        with self.connect() as db:
            all_rules = rows(db)
        return [{k: v for k, v in r.items() if k not in {'citations', 'link_ids'}} |
                {'citation_count': len(r['citations']), 'link_count': len(r['link_ids']), 'current_state': current_state(r)} for r in all_rules]

    def detail(self, rule_id):
        with self.connect() as db:
            db.execute('BEGIN')
            rule = current(db, rule_id)
            combined = merge_packages(self._packages(db))
            history = [json.loads(r[0]) for r in db.execute('SELECT data FROM compliance_revisions WHERE rule_id=? ORDER BY revision', (rule_id,))]
        doc_ids = {c['document_id'] for c in rule['citations']}
        return {'rule': {**rule, 'current_state': current_state(rule)}, 'history': history,
                'documents': [d for d in combined['documents'] if d['id'] in doc_ids],
                'links': [l for l in combined['links'] if l['id'] in rule['link_ids']]}

    def _check_revision(self, rule, body):
        expected = body.get('expected_revision')
        if type(expected) is not int or expected != rule['revision']:
            raise RevisionConflict('Anforderung wurde inzwischen geändert; aktuelle Revision laden')

    def edit(self, rule_id, body):
        if set(body) - EDITABLE - {'expected_revision'}:
            raise ValueError('Unbekannte oder schreibgeschützte Anforderungsfelder')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            prior = current(db, rule_id)
            self._check_revision(prior, body)
            if prior['state'] == 'RETIRED':
                raise ValueError('Quellenlose Anforderung ist zurückgezogen')
            rule = {**prior, **{k: v for k, v in body.items() if k in EDITABLE}}
            rule['title'] = required(rule['title'], 'Titel', 200)
            rule['requirement'] = required(rule['requirement'], 'Anforderung')
            if rule['module'] not in MODULES:
                raise ValueError('Unbekanntes Architekturmodul')
            countries = json.loads((VENDOR / 'jurisdictions.json').read_text())
            for field in ('controls', 'evidence_requirements', 'jurisdictions', 'sectors'):
                value = rule[field]
                if not isinstance(value, list) or not 1 <= len(value) <= 30:
                    raise ValueError(field + ': nichtleere Liste mit höchstens 30 Einträgen erforderlich')
                rule[field] = list(dict.fromkeys(required(v, field, 500) for v in value))
            if any(c not in countries and c != '*' for c in rule['jurisdictions']):
                raise ValueError('Unbekannter Rechtsraum')
            if any(s not in SECTORS for s in rule['sectors']):
                raise ValueError('Unbekannter Sektor')
            if ('*' in rule['jurisdictions'] and len(rule['jurisdictions']) > 1) or ('*' in rule['sectors'] and len(rule['sectors']) > 1):
                raise ValueError('Alle (*) nicht mit einzelnen Geltungsbereichen kombinieren')
            rule.update(state='DRAFT', review=None, edited=True)
            return self._append(db, rule, prior, 'DRAFT_EDITED')

    def review(self, rule_id, body):
        decision = body.get('decision')
        if decision not in {'approve', 'reject'}:
            raise ValueError('Freigabe oder Ablehnung erforderlich')
        reviewer = required(body.get('reviewer'), 'Prüfende Person', 200)
        note = required(body.get('note'), 'Fachliche Begründung')
        review = {'reviewer': reviewer, 'note': note, 'reviewed_utc': timestamp(), 'source_verification': 'SELF_REPORTED_LOCAL_REVIEW'}
        if decision == 'approve':
            review['source_review_reference'] = required(body.get('source_review_reference'), 'Dokumentierter Quellenprüfvermerk', 1000)
            try:
                due = dt.date.fromisoformat(body.get('review_due', ''))
            except (TypeError, ValueError):
                raise ValueError('Wiedervorlage als Datum YYYY-MM-DD erforderlich')
            if due < dt.datetime.now(dt.timezone.utc).date():
                raise ValueError('Wiedervorlage darf nicht in der Vergangenheit liegen')
            review['review_due'] = due.isoformat()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            prior = current(db, rule_id)
            self._check_revision(prior, body)
            if prior['state'] != 'DRAFT':
                raise ValueError('Nur ein aktueller Entwurf kann fachlich entschieden werden')
            if decision == 'approve' and (not prior['jurisdictions'] or not prior['sectors'] or not prior['controls'] or not prior['evidence_requirements'] or not prior['citations']):
                raise ValueError('Vor Freigabe Geltungsbereich, Kontrollen, Nachweise und Quellen pflegen')
            return self._append(db, {**prior, 'state': 'APPROVED_FOR_PLANNING' if decision == 'approve' else 'REJECTED', 'review': review}, prior, 'PLANNING_APPROVED' if decision == 'approve' else 'DRAFT_REJECTED', reviewer)

    def snapshot(self, org):
        with self.connect() as db:
            db.execute('BEGIN')
            all_rules = rows(db)
            packages = self._packages(db)
        applied, pending, versions = [], [], []
        for rule in all_rules:
            state = current_state(rule)
            versions.append({'id': rule['id'], 'revision': rule['revision'], 'state': state, 'sha256': fingerprint(rule)})
            matches = ('*' in rule['jurisdictions'] or bool(set(org['jurisdictions']) & set(rule['jurisdictions']))) and ('*' in rule['sectors'] or org['sector'] in rule['sectors'])
            if state == 'APPROVED_FOR_PLANNING' and matches:
                applied.append({**rule, 'evidence_status': 'NOT_ASSESSED', 'applicability': 'LOCAL_PLANNING_SCOPE_NOT_LEGAL_DETERMINATION'})
            elif state in {'DRAFT', 'REVIEW_OVERDUE'}:
                pending.append({'id': rule['id'], 'revision': rule['revision'], 'state': state})
        combined = merge_packages(packages)
        doc_ids = {c['document_id'] for rule in applied for c in rule['citations']}
        link_ids = {lid for rule in applied for lid in rule['link_ids']}
        return {'mode': 'LOCAL_REVIEWED_PLANNING', 'applied_rules': applied, 'pending_review': pending,
            'rule_versions': versions, 'package_versions': [{'id': p['id'], 'digest': p['digest']} for p in packages],
            'documents': [d for d in combined['documents'] if d['id'] in doc_ids],
            'hyperlinks': [l for l in combined['links'] if l['id'] in link_ids],
            'legal_compliance_verified': False, 'access_granted': False, 'scope_matching': 'Explicit jurisdictions and sectors; EU membership is not inferred'}

    def events(self):
        with self.connect() as db:
            return [{'sequence': r[0], **json.loads(r[1])} for r in db.execute('SELECT sequence, data FROM compliance_events ORDER BY sequence DESC LIMIT 100')]

    def package_version(self, package_id, digest):
        with self.connect() as db:
            row = db.execute('SELECT data FROM compliance_package_history WHERE id=? AND digest=?', (package_id, digest)).fetchone()
        if row is None:
            raise KeyError('Quellenpaketversion nicht gefunden')
        return json.loads(row[0])
