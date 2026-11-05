"""Offline CSV intake. Domain and institution classifications are unverified hints.

No resolver, HTTP client, login flow, signer or authorization service is used here.
Source hashes cover the UTF-8 encoding of the supplied text, including a BOM when
the text stream preserves one. Original input files are never modified.
"""
import csv
from datetime import datetime, timezone
import hashlib
import ipaddress
import itertools
import json
import re
import unicodedata
from urllib.parse import parse_qsl, urlsplit, urlunsplit
import uuid


MAX_ROWS = 72_000
MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_URL_LENGTH = 4096
PAGE_SIZE = 25
SUPPORTED_COUNTRY_HINTS = ('DE', 'ES', 'IT', 'IE', 'CH', 'DK', 'FI', 'SE',
                           'PT', 'FR', 'BE', 'LU', 'EU', 'US')
HEADER_NAMES = {'url', 'urls', 'website', 'webseite', 'domain', 'domains',
                'webadresse', 'web address', 'link', 'uri'}
COUNTRY_TLDS = {code.lower(): code for code in SUPPORTED_COUNTRY_HINTS}
COUNTRY_TLDS['swiss'] = 'CH'
SENSITIVE_KEYS = {'password', 'passwd', 'pwd', 'secret', 'clientsecret', 'token',
                  'accesstoken', 'refreshtoken', 'idtoken', 'apikey', 'authorization',
                  'auth', 'jwt', 'session', 'sessionid', 'credential', 'credentials',
                  'privatekey', 'secretkey', 'signature', 'sig', 'code', 'csrftoken',
                  'oauthtoken', 'oauthverifier', 'clientassertion', 'assertion',
                  'xamzsignature', 'xamzcredential', 'xgoogsignature',
                  'xgoogcredential', 'subscriptionkey'}
LOCAL_SUFFIXES = ('.localhost', '.local', '.internal', '.test', '.invalid',
                  '.example', '.lan', '.home', '.onion', '.localdomain')
REGISTRY_HINTS = {'denic.de', 'nic.it', 'nic.ch', 'switch.ch', 'eurid.eu',
                  'dominios.es', 'afnic.fr', 'dnsbelgium.be', 'dns.lu', 'dns.pt',
                  'punktum.dk', 'internetstiftelsen.se', 'traficom.fi'}
csv.field_size_limit(1_000_000)


def normalize_url(value):
    """Return (canonical URL, IDNA domain), raising a secret-free ValueError."""
    if not isinstance(value, str):
        raise ValueError('URL must be text')
    value = value.strip()
    if not value:
        raise ValueError('URL is empty')
    if len(value) > MAX_URL_LENGTH:
        raise ValueError('URL exceeds length limit')
    if any(char.isspace() or unicodedata.category(char).startswith('C') for char in value):
        raise ValueError('URL contains whitespace or control characters')
    if '\\' in value or re.search(r'%(?:0[0-9a-f]|1[0-9a-f]|7f)', value, re.I):
        raise ValueError('URL contains unsafe separators or control characters')
    if value.startswith('//'):
        value = 'https:' + value
    elif not re.match(r'^https?://', value, re.I):
        if re.match(r'^[a-z][a-z0-9+.-]*://', value, re.I):
            raise ValueError('Only HTTP and HTTPS URLs are supported')
        value = 'https://' + value
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in ('http', 'https'):
            raise ValueError('Only HTTP and HTTPS URLs are supported')
        if parsed.username is not None or parsed.password is not None or '@' in parsed.netloc:
            raise ValueError('Credential-bearing URLs are not accepted')
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        raise ValueError('URL authority is invalid or contains credentials') from None
    if not hostname:
        raise ValueError('URL has no domain')
    try:
        domain = hostname.rstrip('.').encode('idna').decode('ascii').lower()
    except (UnicodeError, ValueError):
        raise ValueError('Domain cannot be encoded as IDNA') from None
    try:
        ipaddress.ip_address(domain)
    except ValueError:
        pass
    else:
        raise ValueError('IP address URLs are not accepted')
    labels = domain.split('.')
    if (len(domain) > 253 or len(labels) < 2 or domain.endswith(LOCAL_SUFFIXES)
            or labels[-1].isdigit()
            or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
                   for label in labels)):
        raise ValueError('A public domain name is required')
    if port is not None and not 1 <= port <= 65535:
        raise ValueError('URL port is invalid')
    for key, _ in parse_qsl(parsed.query, keep_blank_values=True):
        normalized_key = re.sub(r'[^a-z0-9]', '', key.casefold())
        if normalized_key in SENSITIVE_KEYS:
            raise ValueError('Sensitive query parameters are not accepted')
    scheme = parsed.scheme.lower()
    authority = domain
    if port is not None and port != {'http': 80, 'https': 443}[scheme]:
        authority += ':' + str(port)
    result = urlunsplit((scheme, authority, parsed.path or '/', parsed.query, ''))
    if len(result) > MAX_URL_LENGTH:
        raise ValueError('URL exceeds length limit')
    return result, domain


def _is_domain(domain, suffix):
    return domain == suffix or domain.endswith('.' + suffix)


def classify_domain(domain):
    """Classify lexical hints, never an organization's actual jurisdiction."""
    tld = domain.rsplit('.', 1)[-1]
    jurisdiction = COUNTRY_TLDS.get(tld, 'UNKNOWN')
    institution = 'UNKNOWN'
    basis = ['COUNTRY_CODE_TLD:.' + tld] if jurisdiction != 'UNKNOWN' else []
    context_kind = 'GEOGRAPHIC_HINT' if jurisdiction != 'UNKNOWN' else 'UNKNOWN'
    if jurisdiction == 'EU':
        context_kind = 'SUPRANATIONAL_CONTEXT'
        basis = ['REGIONAL_TLD_HINT:.eu']
    if tld in ('gov', 'mil'):
        jurisdiction = 'US'
        institution = 'GOVERNMENT' if tld == 'gov' else 'MILITARY'
        basis = ['RESTRICTED_TLD_HINT:.' + tld]
        context_kind = 'GEOGRAPHIC_HINT'
    elif tld == 'bank':
        institution = 'FINANCE'
        basis.append('SECTOR_TLD_HINT:.bank')
    if _is_domain(domain, 'europa.eu'):
        jurisdiction, institution = 'EU', 'EU_INSTITUTION'
        basis = ['INSTITUTIONAL_DOMAIN_HINT:europa.eu']
        context_kind = 'SUPRANATIONAL_CONTEXT'
    elif _is_domain(domain, 'nato.int'):
        jurisdiction, institution = 'NATO', 'INTERNATIONAL_ORGANIZATION'
        basis = ['INSTITUTIONAL_DOMAIN_HINT:nato.int']
        context_kind = 'INSTITUTIONAL_CONTEXT'
    elif any(_is_domain(domain, suffix) for suffix in ('gob.es', 'gov.it', 'gov.ie')):
        institution = 'GOVERNMENT'
        basis.append('GOVERNMENT_DOMAIN_PATTERN_HINT')
    elif any(_is_domain(domain, suffix) for suffix in REGISTRY_HINTS):
        institution = 'DOMAIN_REGISTRY'
        basis.append('KNOWN_REGISTRY_DOMAIN_HINT')
    return {
        'jurisdiction_hint': jurisdiction, 'institution_hint': institution,
        'hint_basis': basis, 'jurisdiction_hint_kind': context_kind,
        'classification_status': 'HINT_ONLY_UNVERIFIED', 'jurisdictions': [],
    }


def _profile(domain):
    return {
        'status': 'DISCOVERED', 'technical_status': 'NOT_CHECKED',
        'domain_control_status': 'NOT_CHECKED', 'organization_status': 'NOT_CHECKED',
        'compliance_status': 'NOT_CHECKED', 'auth_status': 'NOT_CHECKED',
        'federation_status': 'NOT_AUTHORIZED', 'access_status': 'NOT_GRANTED',
        'federation_authorized': False, 'access_granted': False,
        'signature_status': 'NOT_SIGNED', 'network_access': 'NONE',
        **classify_domain(domain),
    }


class DomainRegistry:
    def __init__(self, connect):
        self.connect = connect
        with self.connect() as connection:
            connection.execute('''CREATE TABLE IF NOT EXISTS url_registry_urls (
                id TEXT PRIMARY KEY, url TEXT NOT NULL UNIQUE, domain TEXT NOT NULL,
                created_at TEXT NOT NULL, first_batch TEXT NOT NULL)''')
            connection.execute('CREATE INDEX IF NOT EXISTS url_registry_domain_idx '
                               'ON url_registry_urls(domain)')
            connection.execute('''CREATE TABLE IF NOT EXISTS url_registry_batches (
                id TEXT PRIMARY KEY, rows_total INTEGER NOT NULL,
                valid_rows INTEGER NOT NULL, data TEXT NOT NULL)''')

    def import_csv(self, stream, filename='input.csv', url_column=None):
        """Import one atomic batch; invalid URL rows are safely counted and skipped.

        Fatal CSV, encoding, size, column selection and row-quota failures roll back
        the entire batch. url_column is a header name or zero-based integer index.
        """
        source_hash = hashlib.sha256()
        source_bytes = 0

        def lines():
            nonlocal source_bytes
            try:
                for line in stream:
                    if not isinstance(line, str):
                        raise ValueError('CSV stream must contain UTF-8 text')
                    encoded = line.encode('utf-8')
                    source_bytes += len(encoded)
                    if source_bytes > MAX_SOURCE_BYTES:
                        raise ValueError('CSV exceeds the 32 MiB source limit')
                    source_hash.update(encoded)
                    yield line
            except UnicodeError:
                raise ValueError('CSV must contain valid UTF-8 text') from None

        source = iter(lines())
        prefix = list(itertools.islice(source, 32))
        if not prefix:
            raise ValueError('CSV contains no data rows')
        prefix[0] = prefix[0].lstrip('\ufeff')
        sample = ''.join(prefix)[:65536]
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=',;\t').delimiter
        except csv.Error:
            delimiter = ','
        reader = csv.reader(itertools.chain(prefix, source), delimiter=delimiter, strict=True)
        batch_id = str(uuid.uuid4())
        filename = str(filename).replace('\\', '/').rsplit('/', 1)[-1]
        filename = ''.join(c for c in filename if not unicodedata.category(c).startswith('C'))[:200]
        filename = filename or 'input.csv'
        counts = dict(rows_total=0, valid_rows=0, invalid_rows=0, duplicate_rows=0,
                      inserted_urls=0, inserted_domains=0)
        errors = []
        created_at = datetime.now(timezone.utc).isoformat()
        try:
            candidates = []
            while len(candidates) < 21:
                try:
                    row = next(reader)
                except StopIteration:
                    break
                if any(cell.strip() for cell in row):
                    candidates.append((reader.line_num, row))
            if not candidates:
                raise ValueError('CSV contains no data rows')
            first = candidates[0][1]
            names = [cell.strip().casefold() for cell in first]
            header = False
            if isinstance(url_column, bool):
                raise ValueError('URL column must be a header name or zero-based index')
            if isinstance(url_column, int):
                if url_column < 0 or url_column >= len(first):
                    raise ValueError('URL column index is outside the CSV columns')
                selected = url_column
                header = names[selected] in HEADER_NAMES
            elif isinstance(url_column, str):
                matches = [index for index, name in enumerate(names)
                           if name == url_column.strip().casefold()]
                if len(matches) != 1:
                    raise ValueError('Requested URL header is missing or ambiguous')
                selected, header = matches[0], True
            elif url_column is not None:
                raise ValueError('URL column must be a header name or zero-based index')
            else:
                matches = [index for index, name in enumerate(names) if name in HEADER_NAMES]
                if len(matches) > 1:
                    raise ValueError('Multiple URL columns found; choose url_column explicitly')
                if matches:
                    selected, header = matches[0], True
                else:
                    scores = {}
                    for _, row in candidates:
                        for index, cell in enumerate(row):
                            try:
                                normalize_url(cell)
                            except ValueError:
                                continue
                            scores[index] = scores.get(index, 0) + 1
                    if not scores:
                        if len(first) == 1:
                            selected = 0
                        else:
                            raise ValueError('No URL column found; choose url_column explicitly')
                    else:
                        best = max(scores.values())
                        winners = [index for index, score in scores.items() if score == best]
                        if len(winners) != 1:
                            raise ValueError('Ambiguous URL columns; choose url_column explicitly')
                        selected = winners[0]

            def remaining_rows():
                yield from candidates[1:] if header else candidates
                for row in reader:
                    if any(cell.strip() for cell in row):
                        yield reader.line_num, row

            with self.connect() as connection:
                connection.execute('BEGIN IMMEDIATE')
                before_domains = connection.execute(
                    'SELECT COUNT(DISTINCT domain) FROM url_registry_urls').fetchone()[0]
                for row_number, row in remaining_rows():
                    counts['rows_total'] += 1
                    if counts['rows_total'] > MAX_ROWS:
                        raise ValueError('CSV exceeds the 72000 data-row limit')
                    try:
                        if selected >= len(row):
                            raise ValueError('URL column is missing from this row')
                        url, domain = normalize_url(row[selected])
                    except ValueError as error:
                        counts['invalid_rows'] += 1
                        if len(errors) < 20:
                            errors.append({'row': row_number, 'reason': str(error)})
                        continue
                    counts['valid_rows'] += 1
                    cursor = connection.execute(
                        'INSERT OR IGNORE INTO url_registry_urls VALUES (?, ?, ?, ?, ?)',
                        (hashlib.sha256(url.encode('utf-8')).hexdigest(), url, domain,
                         created_at, batch_id))
                    if cursor.rowcount:
                        counts['inserted_urls'] += 1
                    else:
                        counts['duplicate_rows'] += 1
                if not counts['rows_total']:
                    raise ValueError('CSV contains no data rows')
                after_domains = connection.execute(
                    'SELECT COUNT(DISTINCT domain) FROM url_registry_urls').fetchone()[0]
                counts['inserted_domains'] = after_domains - before_domains
                result = {
                    'batch_id': batch_id, 'filename': filename,
                    'source_sha256': source_hash.hexdigest(),
                    'source_hash_encoding': 'UTF-8 text including BOM when present',
                    'source_bytes': source_bytes, 'created_at': created_at,
                    'url_column': selected, 'delimiter': delimiter,
                    'error_samples': errors, 'network_access': 'NONE', **counts,
                }
                connection.execute('INSERT INTO url_registry_batches VALUES (?, ?, ?, ?)',
                                   (batch_id, counts['rows_total'], counts['valid_rows'],
                                    json.dumps(result, ensure_ascii=False)))
                return result
        except csv.Error:
            raise ValueError('CSV format is invalid or a field exceeds the size limit') from None

    def summary(self):
        with self.connect() as connection:
            urls, domains = connection.execute(
                'SELECT COUNT(*), COUNT(DISTINCT domain) FROM url_registry_urls').fetchone()
            batches, imported = connection.execute(
                'SELECT COUNT(*), COALESCE(SUM(rows_total), 0) FROM url_registry_batches').fetchone()
        return {'urls': urls, 'domains': domains, 'batches': batches, 'rows_imported': imported,
                'status': 'DISCOVERED', 'signature_status': 'NOT_SIGNED',
                'network_access': 'NONE', 'supported_country_hints': list(SUPPORTED_COUNTRY_HINTS),
                'institutional_context_hints': ['NATO'],
                'classification_status': 'HINT_ONLY_UNVERIFIED'}

    @staticmethod
    def _filter(query, page):
        query = str(query).strip()
        if len(query) > 200:
            raise ValueError('Search query exceeds 200 characters')
        if isinstance(page, bool):
            raise ValueError('Page must be a positive integer')
        try:
            parsed_page = int(page)
        except (ValueError, TypeError):
            raise ValueError('Page must be a positive integer') from None
        if parsed_page < 1 or str(parsed_page) != str(page):
            raise ValueError('Page must be a positive integer')
        if parsed_page > (2 ** 63 - 1) // PAGE_SIZE:
            raise ValueError('Page exceeds the supported range')
        escaped = query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        return '%' + escaped + '%', parsed_page

    def entries(self, query='', page=1):
        pattern, page = self._filter(query, page)
        with self.connect() as connection:
            total = connection.execute(
                "SELECT COUNT(*) FROM url_registry_urls WHERE url LIKE ? ESCAPE '\\'",
                (pattern,)).fetchone()[0]
            rows = connection.execute(
                "SELECT id, url, domain, created_at, first_batch FROM url_registry_urls "
                "WHERE url LIKE ? ESCAPE '\\' ORDER BY url LIMIT ? OFFSET ?",
                (pattern, PAGE_SIZE, (page - 1) * PAGE_SIZE)).fetchall()
        results = [dict(id=row[0], url=row[1], domain=row[2], created_at=row[3],
                        first_batch=row[4], **_profile(row[2])) for row in rows]
        return {'results': results, 'total': total, 'page': page,
                'pages': max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE), 'page_size': PAGE_SIZE}

    def domains(self, query='', page=1):
        pattern, page = self._filter(query, page)
        with self.connect() as connection:
            total = connection.execute(
                "SELECT COUNT(DISTINCT domain) FROM url_registry_urls "
                "WHERE domain LIKE ? ESCAPE '\\'", (pattern,)).fetchone()[0]
            rows = connection.execute(
                "SELECT domain, COUNT(*) FROM url_registry_urls "
                "WHERE domain LIKE ? ESCAPE '\\' GROUP BY domain ORDER BY domain LIMIT ? OFFSET ?",
                (pattern, PAGE_SIZE, (page - 1) * PAGE_SIZE)).fetchall()
        results = [dict(domain=row[0], url_count=row[1], **_profile(row[0])) for row in rows]
        return {'results': results, 'total': total, 'page': page,
                'pages': max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE), 'page_size': PAGE_SIZE}

    def export_csv(self):
        import io
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow(['url', 'domain', 'status', 'jurisdiction_hint', 'institution_hint',
                         'classification_status', 'jurisdictions', 'technical_status',
                         'domain_control_status', 'organization_status', 'compliance_status',
                         'auth_status', 'federation_authorized', 'access_granted', 'signature_status'])
        with self.connect() as connection:
            for url, domain in connection.execute('SELECT url, domain FROM url_registry_urls ORDER BY url'):
                profile = _profile(domain)
                writer.writerow([url, domain, profile['status'], profile['jurisdiction_hint'],
                                 profile['institution_hint'], profile['classification_status'], '[]',
                                 'NOT_CHECKED', 'NOT_CHECKED', 'NOT_CHECKED', 'NOT_CHECKED',
                                 'NOT_CHECKED', 'false', 'false', 'NOT_SIGNED'])
        return output.getvalue()
