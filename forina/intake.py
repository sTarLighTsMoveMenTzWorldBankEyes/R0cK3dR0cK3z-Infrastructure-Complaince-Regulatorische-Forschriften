"""Deterministic document/link intake. Archive text is data, never executable policy."""
import hashlib
import ipaddress
import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

MODULES = {
    'policy_engine': 'Regulatory Policy Engine',
    'organization_registry': 'Organisationsregister',
    'connector_gateway': 'Connector-Gateway',
    'identity_trust': 'Identität & Trust',
    'infrastructure': 'Infrastruktur',
    'data_protection': 'Datenschutz & Datenhaltung',
    'evidence_ledger': 'Nachweise & Provenienz',
    'governance_review': 'Governance & Freigabe',
}
SECTORS = {'general', 'finance', 'critical', 'crypto', 'platform', 'ai', 'government', '*'}
TEXT_SUFFIXES = {'.md', '.txt', '.json', '.yaml', '.yml', '.rego', '.py', '.ts', '.tsx', '.js', '.rs', '.html', '.sh',
    '.toml', '.sql', '.hcl', '.conf', '.css', '.cjs', '.mjs', '.csv', '.example', '.cron', '.service', '.timer', '.lock', '.wasmhost'}
TEXT_NAMES = {'Dockerfile', 'LICENSE', 'Makefile', '.gitignore', '.gitkeep'}
URL_PATTERN = re.compile(r'https?://[^\s<>"\x27`\[\]{}\\]+', re.I)
# Domain hints identify a potential publisher, not authenticity or legal authority.
PUBLISHER_HOSTS = {'eur-lex.europa.eu', 'commission.europa.eu', 'digital-strategy.ec.europa.eu',
    'finance.ec.europa.eu', 'www.gesetze-im-internet.de', 'www.bsi.bund.de', 'www.bafin.de',
    'www.bfdi.bund.de', 'www.un.org', 'www.ohchr.org', 'www.unicef.org', 'www.unicef.de',
    'uscode.house.gov', 'www.ftc.gov', 'www.finma.ch', 'www.edoeb.admin.ch', 'www.mas.gov.sg',
    'www.gov.br', 'www.pdpc.gov.sg', 'www.iso.org'}

def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()

def fingerprint(value):
    return hashlib.sha256(encoded(value)).hexdigest()

def normalize_link(raw):
    if not isinstance(raw, str):
        return None
    raw = raw.rstrip('.,;:*!')
    # Markdown closing delimiters are not part of a URL; retain balanced parentheses.
    while raw.endswith(')') and raw.count(')') > raw.count('('):
        raw = raw[:-1]
    try:
        parsed = urlsplit(raw)
        host = (parsed.hostname or '').rstrip('.').encode('idna').decode('ascii').lower()
        port = parsed.port
        if parsed.scheme.lower() not in {'http', 'https'} or parsed.username or parsed.password:
            return None
        if '.' not in host or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]*[a-z0-9])?', label) for label in host.split('.')):
            return None
        try:
            ipaddress.ip_address(host)
            return None
        except ValueError:
            pass
        if host.endswith(('.localhost', '.local', '.internal', '.example', '.invalid', '.test')) or host in {'example.org', 'example.com', 'example.net'}:
            return None
        query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if not k.lower().startswith('utm_')]
        if any(k.lower() in {'token', 'api_key', 'apikey', 'password', 'access_token', 'secret'} for k, _ in query):
            return None
        authority = host + (f':{port}' if port and port != (443 if parsed.scheme.lower() == 'https' else 80) else '')
        url = urlunsplit((parsed.scheme.lower(), authority, parsed.path or '/', urlencode(query), parsed.fragment))
        if len(url) > 2000:
            return None
        return {'id': 'link-' + fingerprint(url)[:24], 'url': url, 'host': host,
                'publisher_hint': 'INSTITUTIONAL_DOMAIN_HINT' if host in PUBLISHER_HOSTS else 'OTHER_DOMAIN',
                'verification': 'NOT_FETCHED', 'citations': []}
    except (ValueError, UnicodeError):
        return None

EXTRA_LAWS = {
    'GG': ('Grundgesetz', r'\bGrundgesetz\b|\bArt\.?\s*\d+\s*GG\b|\bGG\s+Art\b'),
    'EU_CHARTER': ('EU-Grundrechtecharta', r'EU[- ]Charta|Charta der Grundrechte|Grundrechtecharta'),
    'UN_CHARTER': ('Charta der Vereinten Nationen', r'UN[- ]Charta|UN Charter'),
    'UDHR': ('Allgemeine Erklärung der Menschenrechte', r'\bAEMR\b|Universal Declaration of Human Rights|Allgemeine Erklärung der Menschenrechte'),
    'UN_CRC': ('UN-Kinderrechtskonvention', r'Kinderrechtskonvention|\bUN[- ]KRK\b'),
    'ISO27001': ('ISO/IEC 27001', r'\bISO(?:/IEC)?[- ]*27001\b'),
    'ISO42001': ('ISO/IEC 42001', r'\bISO(?:/IEC)?[- ]*42001\b'),
}
ALIASES = {
    'GDPR': r'\bDSGVO\b|\bGDPR\b|Datenschutzgrundverordnung|/2016/679/',
    'EU_AI_ACT': r'\bAI[- ]Act\b|EU[- ]AI[- ]Act|KI[- ]Verordnung|/2024/1689/|regulatory-framework-ai',
    'NIS2': r'\bNIS[- ]?2\b|/2022/2555/', 'DORA': r'\bDORA\b|/2022/2554/',
    'EIDAS': r'\beIDAS\b|/910/2014/|eu-trusted-lists', 'MICA': r'\bMiCA\b|/2023/1114/',
    'PSD2': r'\bPSD[- ]?2\b|/2015/2366/', 'DSA': r'\bDSA\b|Digital Services Act',
    'DMA': r'\bDMA\b|Digital Markets Act', 'US_FOIA': r'\bFOIA\b|Freedom of Information Act',
    'US_SUNSHINE': r'Government in the Sunshine Act|US Sunshine',
}

# These are architecture proposals; they are not extracted verbatim legal duties.
PROPOSALS = {
    'GDPR': ('data_protection', ['Verarbeitungszwecke und Datenumfang dokumentieren', 'Lösch- und Berechtigungskonzept prüfen'], ['Verarbeitungsverzeichnis', 'Löschkonzept und Berechtigungsprüfung']),
    'EU_AI_ACT': ('governance_review', ['KI-Systeme und Rollen inventarisieren', 'Risikoeinstufung und menschliche Aufsicht fachlich beurteilen'], ['KI-Inventar', 'Begründete Risikoeinstufung und Aufsichtskonzept']),
    'NIS2': ('infrastructure', ['Einrichtungs- und Sektorrelevanz prüfen', 'Risikomanagement und Vorfallabläufe dokumentieren'], ['Anwendbarkeitsbewertung', 'Incident- und Risikomanagementkonzept']),
    'DORA': ('infrastructure', ['Finanzsektor-Relevanz und IKT-Dienstleister dokumentieren', 'Resilienz- und Vorfallprozesse prüfen'], ['IKT-Inventar', 'Resilienz- und Drittparteienbewertung']),
    'EIDAS': ('identity_trust', ['Vertrauensdienst und Status unterscheiden', 'Vertrauensanker und Widerrufsprüfung dokumentieren'], ['Trust-Chain-Prüfprotokoll', 'Quellen- und Statusnachweis']),
    'G01': ('identity_trust', ['Autorisierung und Ablauf der TXT-Challenge dokumentieren'], ['Freigabereferenz', 'Challenge- und Ablaufprotokoll']),
    'G02': ('organization_registry', ['Registrierungsdaten als Hinweis mit Quelle kennzeichnen'], ['RDAP-/Registry-Quelle und Identitätsbewertung']),
    'G03': ('organization_registry', ['Organisationsidentität unabhängig abgleichen'], ['Registerauszug oder verifizierter LEI-/vLEI-Nachweis']),
    'G04': ('organization_registry', ['Zulassung auf zuständige Aufsicht und Tätigkeit beziehen'], ['Quellenbezogener Zulassungs- und Tätigkeitsnachweis']),
    'G05': ('identity_trust', ['Trust Anchors und Signaturketten unabhängig prüfen'], ['Trust-Anchor- und Signaturprüfprotokoll']),
    'G06': ('identity_trust', ['Zertifikatsart und Rechtswirkung getrennt erfassen'], ['Zertifikatstyp und validierter Statusnachweis']),
    'G07': ('infrastructure', ['DNSSEC-Status und Validierungsergebnis getrennt erfassen'], ['DNSSEC-Prüfprotokoll']),
    'G08': ('governance_review', ['Zustimmung und Berechtigungsprüfung dokumentieren'], ['Zustimmungsnachweis', 'Unabhängige Berechtigungsprüfung']),
    'G09': ('connector_gateway', ['DNS-Connector auf erlaubte Zonen und TXT-Einträge begrenzen'], ['Berechtigungs- und Zonenkonfiguration']),
    'G10': ('data_protection', ['Geheimnisse aus Protokollen und Exporten ausschließen'], ['Redaktions- und Logging-Konzept']),
    'G11': ('data_protection', ['Zweckbindung, Löschung und Datenminimierung dokumentieren'], ['Daten- und Löschkonzept']),
    'G12': ('connector_gateway', ['Domainkontrolle und Zugangsberechtigung unabhängig entscheiden'], ['Berechtigungsmodell und Entscheidungstrennung']),
    'G13': ('evidence_ledger', ['Gültigkeit und Widerruf der Nachweise nachhalten'], ['Gültigkeits- und Widerrufsprotokoll']),
    'G14': ('policy_engine', ['Unklare oder fehlerhafte Prüfungen ohne positive Freigabe beenden'], ['Negativ- und Fehlerfalltests']),
    'G15': ('data_protection', ['Öffentliche und eingeschränkte Informationen klassifizieren'], ['Informationsklassifizierung und Offenlegungsprüfung']),
    'G16': ('policy_engine', ['Niederlassung, Tätigkeit, Rolle und Datum für die Prüfung erfassen'], ['Begründete Geltungsbereichsentscheidung']),
    'G17': ('governance_review', ['Unabhängige fachliche Freigabe dokumentieren'], ['Freigabevermerk mit Begründung']),
    'G18': ('data_protection', ['Lokale Datenhaltung und autorisierte Netzabrufe abgrenzen'], ['Datenfluss- und Netzfreigabekonzept']),
    'G19': ('infrastructure', ['Softwareherkunft und Abhängigkeiten nachweisen'], ['Build- und Abhängigkeitsnachweis']),
    'G20': ('connector_gateway', ['Quellenkatalogisierung von Enrollment und Konfigurationsänderungen trennen'], ['Connector-Aktionsmodell und Freigaben']),
    'G21': ('governance_review', ['Rechtsträger und Geltung von Offenlegungsregeln prüfen'], ['Fachliche FOIA-/Sunshine-Anwendbarkeitsbewertung']),
    'G22': ('evidence_ledger', ['Status bei Entzug, Transfer oder Prüfanlass zurücksetzen'], ['Widerrufs- und Rezertifizierungsablauf']),
    'G23': ('connector_gateway', ['Zielzugriffe begrenzen und URL-Abrufe gesondert prüfen'], ['Connector- und Zielprüfung']),
    'G24': ('identity_trust', ['Vertrauensstatus ohne unbelegte CA- oder eIDAS-Behauptung darstellen'], ['Statusmodell und Kommunikationsprüfung']),
}

def proposal(code, title, kind, requirement=None):
    module, controls, evidence = PROPOSALS.get(code, ('policy_engine', ['Anwendbarkeit, Rollen und konkrete Pflichten fachlich dokumentieren'], ['Begründete Anwendbarkeitsbewertung', 'Quellenbezogener Prüfvermerk']))
    return {'id': ('control:' if kind == 'INTERNAL_CONTROL' else 'law:') + code,
        'code': code, 'title': title, 'kind': kind,
        'requirement': requirement or f'Anwendbarkeit und konkrete Anforderungen von {title} anhand von Tätigkeit, Rolle, Rechtsraum und Zeitpunkt prüfen.',
        'module': module, 'controls': controls, 'evidence_requirements': evidence,
        'jurisdictions': [], 'sectors': [], 'citations': [], 'link_ids': [],
        'mapping_basis': 'ARCHITECTURE_PROPOSAL_REQUIRES_REVIEW', 'legal_verified': False}

def extract_document(title, content, origin, definitions, project_id=None, source_url=None):
    doc_id = 'doc-' + fingerprint([origin, title])[:24]
    source_hash = hashlib.sha256(content.encode()).hexdigest()
    document = {'id': doc_id, 'title': title, 'origin': origin, 'project_id': project_id,
        'sha256': source_hash, 'line_count': len(content.splitlines()), 'source_url': None,
        'interpretation': 'UNVERIFIED_SOURCE_TEXT'}
    links, candidates = {}, {}
    patterns = {code: re.compile(ALIASES.get(code, r'(?!)') + r'|(?<!\w)' + re.escape(code) + r'(?!\w)', re.I) for code in definitions}
    patterns.update({code: re.compile(pattern, re.I) for code, (_, pattern) in EXTRA_LAWS.items()})
    legal_text = title.lower().endswith(('.md', '.txt')) or origin == 'MANUAL_DOCUMENT'
    if source_url:
        link = normalize_link(source_url)
        if link is None:
            raise ValueError('Quell-URL muss eine öffentliche http/https-Adresse ohne Zugangsdaten sein')
        document['source_url'] = link['url']
        link['citations'].append({'document_id': doc_id, 'source_sha256': source_hash, 'line': 0})
        links[link['id']] = link
    for number, line in [(0, title), *enumerate(content.splitlines(), 1)]:
        line_links = []
        for match in URL_PATTERN.finditer(line):
            link = normalize_link(match.group())
            if link is not None:
                existing = links.setdefault(link['id'], link)
                citation = {'document_id': doc_id, 'source_sha256': source_hash, 'line': number}
                if citation not in existing['citations']:
                    existing['citations'].append(citation)
                line_links.append(link['id'])
        if not legal_text:
            continue
        for code, pattern in patterns.items():
            match = pattern.search(line)
            if not match:
                continue
            name = EXTRA_LAWS[code][0] if code in EXTRA_LAWS else definitions[code]['title']
            candidate = candidates.setdefault(code, proposal(code, name, 'STANDARD_REFERENCE' if code.startswith('ISO') else 'LEGAL_REFERENCE'))
            start = max(0, match.start() - 100)
            candidate['citations'].append({'document_id': doc_id, 'source_sha256': source_hash, 'line': number, 'column': match.start() + 1, 'quote': line[start:start+500].strip(), 'relation': 'TITLE_ONLY_NOT_OBLIGATION' if number == 0 else 'MENTION_NOT_OBLIGATION'})
            candidate['link_ids'] = sorted(set(candidate['link_ids'] + line_links))
    # Parse only known schemas, never execute archive scripts or arbitrary rules.
    name = title.rsplit('/', 1)[-1]
    if name in {'laws.json', 'guardrails.json'}:
        try:
            data = json.loads(content)
        except ValueError:
            data = None
        if name == 'laws.json' and isinstance(data, dict):
            for code, law in data.items():
                if not isinstance(law, dict) or not isinstance(law.get('title'), str):
                    continue
                candidate = proposal(code, law['title'], 'REGULATORY_CATALOG_ENTRY')
                pointer = '/' + code.replace('~', '~0').replace('/', '~1')
                candidate['citations'] = [{'document_id': doc_id, 'source_sha256': source_hash, 'pointer': pointer, 'quote': law['title'], 'relation': 'IMPORTED_CATALOG_ENTRY'}]
                link = normalize_link(law.get('official_source', ''))
                if link:
                    candidate['link_ids'] = [link['id']]
                candidates[code] = candidate
        if name == 'guardrails.json' and isinstance(data, list):
            for i, control in enumerate(data):
                if not isinstance(control, dict) or not all(isinstance(control.get(k), str) and control[k] for k in ('id', 'title', 'requirement')):
                    continue
                candidate = proposal(control['id'], control['title'], 'INTERNAL_CONTROL', control['requirement'])
                candidate['citations'] = [{'document_id': doc_id, 'source_sha256': source_hash, 'pointer': '/' + str(i), 'quote': control['requirement'], 'relation': 'ARCHIVE_INTERNAL_REQUIREMENT'}]
                candidates[control['id']] = candidate
    if title.endswith('.rego'):
        code = 'OPA_' + fingerprint([origin, title])[:12].upper()
        candidate = proposal(code, 'Software-Policy: ' + name, 'SOFTWARE_POLICY', 'Archivierte OPA-Policy fachlich und technisch prüfen; keine automatische Ausführung oder Rechtswirkung.')
        candidate['module'] = 'connector_gateway'
        candidate['citations'] = [{'document_id': doc_id, 'source_sha256': source_hash, 'line': 1, 'quote': content[:500], 'relation': 'SOFTWARE_POLICY_NOT_LEGISLATION'}]
        candidates[code] = candidate
    for candidate in candidates.values():
        if document['source_url']:
            candidate['link_ids'] = sorted(set(candidate['link_ids'] + [normalize_link(document['source_url'])['id']]))
        for citation in candidate['citations']:
            citation['document_version'] = fingerprint(document)
    return {'document': document, 'links': list(links.values()), 'candidates': list(candidates.values())}

def merge_materials(materials):
    documents, links, rules = {}, {}, {}
    for material in materials:
        documents[material['document']['id']] = material['document']
        for link in material['links']:
            existing = links.setdefault(link['id'], {**link, 'citations': []})
            existing['citations'].extend(c for c in link['citations'] if c not in existing['citations'])
        for rule in material['candidates']:
            existing = rules.setdefault(rule['id'], {**rule, 'citations': [], 'link_ids': []})
            existing['citations'].extend(c for c in rule['citations'] if c not in existing['citations'])
            existing['link_ids'] = sorted(set(existing['link_ids'] + rule['link_ids']))
    return {'documents': sorted(documents.values(), key=lambda d: d['id']),
        'links': sorted(links.values(), key=lambda l: l['id']), 'candidates': sorted(rules.values(), key=lambda r: r['id'])}
