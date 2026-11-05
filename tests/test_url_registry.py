"""Offline registry tests, including a synthetic full-capacity atomic import."""
from contextlib import contextmanager
import csv
import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from forina.url_registry import DomainRegistry, MAX_ROWS, normalize_url


class URLRegistryTests(unittest.TestCase):
    def setUp(self):
        self.storage = tempfile.TemporaryDirectory(prefix='forina-url-test-')
        self.addCleanup(self.storage.cleanup)
        self.path = self.storage.name + '/registry.sqlite'

        @contextmanager
        def connect():
            connection = sqlite3.connect(self.path)
            try:
                with connection:
                    yield connection
            finally:
                connection.close()

        self.registry = DomainRegistry(connect)

    def load(self, content, **options):
        return self.registry.import_csv(io.StringIO(content, newline=''), **options)

    def test_bom_semicolon_normalization_and_global_deduplication(self):
        content = '\ufeffWebseite;Label\r\nHTTPS://BÜCHER.de:443/Path?a=2#fragment;one\r\n' \
                  'https://xn--bcher-kva.de/Path?a=2;two\r\n'
        result = self.load(content, filename='/private/path/source.csv')
        self.assertEqual(result['delimiter'], ';')
        self.assertEqual(result['filename'], 'source.csv')
        self.assertEqual(result['source_sha256'], hashlib.sha256(content.encode('utf-8')).hexdigest())
        self.assertEqual(result['source_bytes'], len(content.encode('utf-8')))
        self.assertEqual(result['rows_total'], 2)
        self.assertEqual(result['valid_rows'], 2)
        self.assertEqual(result['inserted_urls'], 1)
        self.assertEqual(result['inserted_domains'], 1)
        self.assertEqual(result['duplicate_rows'], 1)
        again = self.load('URL\nhttps://xn--bcher-kva.de/Path?a=2\n')
        self.assertEqual(again['duplicate_rows'], 1)
        self.assertEqual(again['inserted_urls'], 0)
        self.assertEqual(again['inserted_domains'], 0)
        entry = self.registry.entries()['results'][0]
        self.assertEqual(entry['url'], 'https://xn--bcher-kva.de/Path?a=2')
        self.assertEqual(self.registry.summary()['rows_imported'], 3)

    def test_headerless_auto_column_tab_and_explicit_columns(self):
        result = self.load('1\texample.org/a\n2\texample.net/b\n')
        self.assertEqual(result['delimiter'], '\t')
        self.assertEqual(result['url_column'], 1)
        self.assertEqual(result['inserted_urls'], 2)
        self.assertEqual(self.load('Name,Adresse\nSynthetic,example.com\n',
                                   url_column='Adresse')['inserted_urls'], 1)
        self.assertEqual(self.load('Name,Website\nx,example.eu\n',
                                   url_column=1)['rows_total'], 1)
        self.assertEqual(self.load('Synthetic,example.de\n',
                                   url_column=1)['inserted_urls'], 1)

    def test_ambiguous_and_missing_columns_fail_without_writes(self):
        for content, options in [
            ('URL,Website\nexample.org,example.com\n', {}),
            ('example.org,example.com\n', {}),
            ('URL\nexample.org\n', {'url_column': 'missing'}),
            ('URL\nexample.org\n', {'url_column': -1}),
            ('URL\nexample.org\n', {'url_column': True}),
            ('Name,Value\nAlice,One\n', {}),
            ('URL\n', {}), ('', {}),
        ]:
            with self.subTest(content=content, options=options), self.assertRaises(ValueError):
                self.load(content, **options)
        self.assertEqual(self.registry.summary()['urls'], 0)
        self.assertEqual(self.registry.summary()['batches'], 0)

    def test_invalid_rows_are_counted_without_logging_credentials(self):
        secret = 'SENSITIVE-NEVER-LOG'
        content = 'URL\nexample.org/ok\n' + '\n'.join([
            'https://user:' + secret + '@example.org',
            'https://example.org/?access_token=' + secret,
            'ftp://example.org/file', 'http://127.0.0.1/',
            'http://[::1]/', 'http://localhost/', 'http://service.local/',
            'http://service.internal/', 'http://invalid..org/',
            'http://example.org:99999/', 'http://example.org/%0aheader',
            'http://example.org/a b', 'x' * 5000,
        ]) + '\n'
        result = self.load(content)
        self.assertEqual(result['valid_rows'], 1)
        self.assertEqual(result['invalid_rows'], 13)
        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn(secret, self.registry.export_csv())
        # Error samples are bounded even for a large invalid batch.
        errors = self.load('URL\n' + 'localhost\n' * 30)
        self.assertEqual(errors['invalid_rows'], 30)
        self.assertEqual(len(errors['error_samples']), 20)

    def test_canonicalization_retains_url_semantics_and_separate_paths(self):
        examples = {
            'example.org': 'https://example.org/',
            '//EXAMPLE.org:443/a#part': 'https://example.org/a',
            'http://EXAMPLE.org.:80/a?x=1&x=2': 'http://example.org/a?x=1&x=2',
            'https://example.org:8443/path': 'https://example.org:8443/path',
        }
        for original, expected in examples.items():
            with self.subTest(original=original):
                self.assertEqual(normalize_url(original)[0], expected)
        result = self.load('URL\nexample.org/a\nexample.org/b\nexample.org/a?x=1\n')
        self.assertEqual(result['inserted_urls'], 3)
        self.assertEqual(result['inserted_domains'], 1)
        self.assertEqual(self.registry.domains()['results'][0]['url_count'], 3)

    def test_classifications_cannot_promote_csv_assertions(self):
        self.load('URL,status,country,federation_authorized\n'
                  'nato.int,ACTIVE,US,true\n'
                  'sub.nato.int,ACTIVE,US,true\n'
                  'nato.int.evil.com,ACTIVE,US,true\n'
                  'europa.eu,ACTIVE,US,true\n'
                  'europa.eu.evil.com,ACTIVE,US,true\n'
                  'example.bank,ACTIVE,US,true\n'
                  'example.com,ACTIVE,CH,true\n'
                  'example.gov,ACTIVE,DE,true\n'
                  'example.mil,ACTIVE,DE,true\n')
        entries = {row['domain']: row for row in self.registry.entries()['results']}
        self.assertEqual(entries['nato.int']['jurisdiction_hint'], 'NATO')
        self.assertEqual(entries['sub.nato.int']['jurisdiction_hint_kind'], 'INSTITUTIONAL_CONTEXT')
        self.assertEqual(entries['nato.int.evil.com']['jurisdiction_hint'], 'UNKNOWN')
        self.assertEqual(entries['europa.eu']['institution_hint'], 'EU_INSTITUTION')
        self.assertEqual(entries['europa.eu.evil.com']['institution_hint'], 'UNKNOWN')
        self.assertEqual(entries['example.bank']['jurisdiction_hint'], 'UNKNOWN')
        self.assertEqual(entries['example.bank']['institution_hint'], 'FINANCE')
        self.assertEqual(entries['example.com']['jurisdiction_hint'], 'UNKNOWN')
        self.assertEqual(entries['example.gov']['jurisdiction_hint'], 'US')
        self.assertEqual(entries['example.mil']['jurisdiction_hint'], 'US')
        for entry in entries.values():
            self.assertEqual(entry['status'], 'DISCOVERED')
            self.assertEqual(entry['classification_status'], 'HINT_ONLY_UNVERIFIED')
            self.assertEqual(entry['signature_status'], 'NOT_SIGNED')
            self.assertEqual(entry['jurisdictions'], [])
            self.assertFalse(entry['federation_authorized'])
            self.assertFalse(entry['access_granted'])
            for name in ['technical_status', 'domain_control_status', 'organization_status',
                         'compliance_status', 'auth_status']:
                self.assertEqual(entry[name], 'NOT_CHECKED')

    def test_all_named_country_hints_are_supported_without_legal_assertions(self):
        codes = 'DE ES IT IE CH DK FI SE PT FR BE LU EU US'.split()
        self.load('URL\n' + '\n'.join('example.' + code.lower() for code in codes))
        entries = self.registry.entries()['results']
        self.assertEqual({entry['jurisdiction_hint'] for entry in entries}, set(codes))
        self.assertTrue(all(entry['jurisdictions'] == [] for entry in entries))
        self.assertNotIn('NATO', self.registry.summary()['supported_country_hints'])
        regional = next(row for row in entries if row['domain'] == 'example.eu')
        self.assertEqual(regional['jurisdiction_hint_kind'], 'SUPRANATIONAL_CONTEXT')

    def test_empty_pagination_and_invalid_text_streams(self):
        self.assertEqual(self.registry.entries()['pages'], 1)
        self.assertEqual(self.registry.domains()['pages'], 1)
        for stream in [io.BytesIO(b'URL\nexample.org\n'), io.StringIO('URL\n\ud800\n')]:
            with self.subTest(stream=type(stream).__name__), self.assertRaisesRegex(ValueError, 'UTF-8'):
                self.registry.import_csv(stream)
        with patch('forina.url_registry.MAX_SOURCE_BYTES', 256):
            with self.assertRaisesRegex(ValueError, 'source limit'):
                self.load('URL\n' + 'example.org/\n' * 40)
        self.assertEqual(self.registry.summary()['batches'], 0)
        self.assertEqual(self.registry.summary()['urls'], 0)

    def test_format_failure_rolls_back_the_entire_batch(self):
        self.load('URL\nexisting.org\n')
        # The broken quoted field occurs after the parser's 21-row detection sample.
        content = 'URL\n' + '\n'.join('new.example.org/' + str(i) for i in range(30))
        content += '\n"unterminated\n'
        with self.assertRaisesRegex(ValueError, 'CSV format'):
            self.load(content)
        self.assertEqual(self.registry.summary()['urls'], 1)
        self.assertEqual(self.registry.summary()['batches'], 1)

    def test_full_72000_row_import_deduplicates_and_quota_is_atomic(self):
        # 36,000 distinct URLs across 1,000 domains; each URL occurs twice.
        content = io.StringIO(newline='')
        writer = csv.writer(content)
        writer.writerow(['URL', 'Label'])
        for index in range(MAX_ROWS):
            unique = index % 36_000
            writer.writerow(['https://d%d.example.org/p/%d' % (unique % 1000, unique), 'synthetic'])
        content.seek(0)
        result = self.registry.import_csv(content)
        self.assertEqual(result['rows_total'], 72_000)
        self.assertEqual(result['valid_rows'], 72_000)
        self.assertEqual(result['inserted_urls'], 36_000)
        self.assertEqual(result['duplicate_rows'], 36_000)
        self.assertEqual(result['inserted_domains'], 1000)
        before = self.registry.summary()
        oversized = io.StringIO('URL\n' + 'quota.example.net\n' * (MAX_ROWS + 1))
        with self.assertRaisesRegex(ValueError, '72000'):
            self.registry.import_csv(oversized)
        self.assertEqual(self.registry.summary(), before)
        self.assertEqual(self.registry.entries(query='quota.example.net')['total'], 0)

    def test_pagination_literal_filter_and_export(self):
        self.load('URL\n' + '\n'.join('d%d.example.org/a' % i for i in range(60)))
        self.assertEqual(len(self.registry.entries()['results']), 25)
        self.assertEqual(len(self.registry.entries(page=3)['results']), 10)
        self.assertEqual(self.registry.entries()['pages'], 3)
        self.assertEqual(self.registry.domains()['pages'], 3)
        self.assertEqual(self.registry.entries(query='d1.example.org')['total'], 1)
        self.assertEqual(self.registry.entries(query='%')['total'], 0)
        for page in [0, -1, True, 1.5, 'bad', 2 ** 63]:
            with self.subTest(page=page), self.assertRaises(ValueError):
                self.registry.entries(page=page)
        with self.assertRaises(ValueError):
            self.registry.domains(query='x' * 201)
        rows = list(csv.DictReader(io.StringIO(self.registry.export_csv())))
        self.assertEqual(len(rows), 60)
        self.assertTrue(all(row['status'] == 'DISCOVERED' for row in rows))
        self.assertTrue(all(row['access_granted'] == 'false' for row in rows))
        self.assertTrue(all(row['signature_status'] == 'NOT_SIGNED' for row in rows))


if __name__ == '__main__':
    unittest.main()
