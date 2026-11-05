"""Local-only HTTP workbench; no external service calls."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import io
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .core import GUARDRAILS, Workbench, verify_record
from .compliance import RevisionConflict
from .jurisdictions import resolve_plan
from .gateway_policy import evaluate_gateway

WEB = Path(__file__).resolve().parent / 'web'

def handler(workbench):
    class Handler(BaseHTTPRequestHandler):
        def send(self, status, body, content_type='application/json; charset=utf-8', filename=None):
            raw = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            if filename:
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(raw)

        def allowed_host(self):
            return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}

        def do_GET(self):
            if not self.allowed_host():
                return self.send(403, {'error': 'Nur lokaler Zugriff erlaubt'})
            try:
                url = urlsplit(self.path)
                path = url.path
                if path in {'/', '/app.js', '/compliance.js', '/enrollment.js', '/registry.js', '/style.css'}:
                    name, mime = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/compliance.js': ('compliance.js', 'text/javascript; charset=utf-8'), '/enrollment.js': ('enrollment.js', 'text/javascript; charset=utf-8'), '/registry.js': ('registry.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8')}[path]
                    return self.send(200, (WEB / name).read_bytes(), mime)
                if path == '/api/health':
                    return self.send(200, {'status': 'ok', 'mode': 'LOCAL_WORKBENCH', 'projects': len(workbench.projects())})
                if path == '/api/catalog':
                    return self.send(200, {'projects': workbench.projects(), 'jurisdictions': json.loads((GUARDRAILS / 'jurisdictions.json').read_text())})
                if path == '/api/search':
                    return self.send(200, workbench.search(parse_qs(url.query).get('q', [''])[0]))
                if path == '/api/organizations':
                    return self.send(200, workbench.organizations())
                if path == '/api/records':
                    return self.send(200, workbench.records())
                if path == '/api/forward-auth':
                    return self.send(503, {'error':'AUTHENTICATION_NOT_CONFIGURED','access_granted':False,'reason':'OIDC-Sessionverifier und produktive Zugriffsdurchsetzung sind nicht eingerichtet'})
                if path == '/api/gateway/status':
                    return self.send(200, {'mode':'OFFLINE_DESIGN','pocket_id':'NOT_CONFIGURED','forward_auth':'NOT_IMPLEMENTED','external_auth_discovery':'NOT_PERFORMED','access_granted':False})
                if path == '/api/registry':
                    return self.send(200, workbench.registry.summary())
                if path in {'/api/registry/urls','/api/registry/domains'}:
                    query = parse_qs(url.query)
                    method = workbench.registry.entries if path.endswith('/urls') else workbench.registry.domains
                    return self.send(200, method(query.get('q',[''])[0], int(query.get('page',['1'])[0])))
                if path == '/api/registry/export.csv':
                    return self.send(200, workbench.registry.export_csv().encode('utf-8'), 'text/csv; charset=utf-8', 'forina-master-registry.csv')
                if path == '/api/enrollments':
                    return self.send(200, workbench.enrollment.list())
                if path == '/api/enrollments/test-key':
                    return self.send(200, workbench.enrollment.key_info())
                if path == '/api/compliance':
                    return self.send(200, workbench.compliance.summary())
                if path == '/api/compliance/rules':
                    return self.send(200, workbench.compliance.rules())
                if path == '/api/compliance/sources':
                    query = parse_qs(url.query)
                    return self.send(200, workbench.compliance.sources(query.get('q', [''])[0], int(query.get('page', ['1'])[0])))
                if path == '/api/compliance/events':
                    return self.send(200, workbench.compliance.events())
                parts = [unquote(p) for p in path.strip('/').split('/')]
                if len(parts) == 3 and parts[:2] == ['api', 'enrollments']:
                    return self.send(200, workbench.enrollment.get(parts[2]))
                if len(parts) == 4 and parts[:2] == ['api', 'enrollments'] and parts[3] == 'receipt':
                    enrollment = workbench.enrollment.get(parts[2])
                    if enrollment['receipt'] is None:
                        return self.send(404, {'error':'Noch kein signierter Testnachweis vorhanden'})
                    return self.send(200, enrollment['receipt'], filename='forina-local-test-' + enrollment['id'] + '.json')
                if len(parts) == 4 and parts[:3] == ['api', 'compliance', 'rules']:
                    return self.send(200, workbench.compliance.detail(parts[3]))
                if len(parts) == 5 and parts[:3] == ['api', 'compliance', 'packages']:
                    package = workbench.compliance.package_version(parts[3], parts[4])
                    return self.send(200, package)
                if len(parts) == 4 and parts[:2] == ['api', 'records'] and parts[3] == 'export':
                    record = workbench.record(parts[2])
                    return self.send(200, workbench.export(record['id']), 'application/zip', 'forina-' + record['id'] + '.zip')
                if len(parts) == 4 and parts[:2] == ['api', 'organizations'] and parts[3] == 'plan':
                    return self.send(200, workbench.plan(parts[2]))
                self.send(404, {'error': 'Nicht gefunden'})
            except KeyError as ex:
                self.send(404, {'error': str(ex)})
            except ValueError as ex:
                self.send(400, {'error': str(ex)})
            except Exception:
                self.send(500, {'error': 'Interner Fehler; lokale Daten und Serverprotokoll prüfen'})

        def do_POST(self):
            if not self.allowed_host():
                return self.send(403, {'error': 'Nur lokaler Zugriff erlaubt'})
            origin = self.headers.get('Origin')
            if origin and origin not in {f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'}:
                return self.send(403, {'error': 'Fremder Ursprung abgelehnt'})
            if urlsplit(self.path).path == '/api/registry/import-csv':
                return self.import_csv()
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.send(415, {'error': 'application/json erforderlich'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 5_000_000:
                    return self.send(413, {'error': 'Ungültige Anfragegröße'})
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError('JSON-Objekt erforderlich')
                if self.path == '/api/organizations':
                    return self.send(201, workbench.add_organization(data))
                if self.path == '/api/records':
                    return self.send(201, workbench.create_record(data.get('organization_id', '')))
                if self.path == '/api/verify':
                    return self.send(200, verify_record(data))
                if self.path == '/api/jurisdictions/plan':
                    return self.send(200, resolve_plan(data))
                if self.path == '/api/gateway/plan':
                    return self.send(200, evaluate_gateway(data))
                if self.path == '/api/enrollments':
                    return self.send(201, workbench.enrollment.start(data))
                if self.path == '/api/enrollments/verify-test-receipt':
                    return self.send(200, workbench.enrollment.verify(data))
                if self.path == '/api/compliance/import':
                    return self.send(200, workbench.compliance.import_archives())
                if self.path == '/api/compliance/preview':
                    return self.send(200, workbench.compliance.preview(data))
                if self.path == '/api/compliance/documents':
                    return self.send(200, workbench.compliance.ingest_document(data))
                if self.path == '/api/compliance/rules':
                    return self.send(201, workbench.compliance.create_requirement(data))
                parts = [unquote(p) for p in self.path.strip('/').split('/')]
                if len(parts) == 4 and parts[:2] == ['api', 'enrollments'] and parts[3] == 'simulate':
                    return self.send(200, workbench.enrollment.simulate(parts[2], data))
                if len(parts) == 4 and parts[:2] == ['api', 'enrollments'] and parts[3] == 'revoke':
                    return self.send(200, workbench.enrollment.revoke(parts[2], data))
                if len(parts) == 5 and parts[:3] == ['api', 'compliance', 'rules'] and parts[4] == 'edit':
                    return self.send(200, workbench.compliance.edit(parts[3], data))
                if len(parts) == 5 and parts[:3] == ['api', 'compliance', 'rules'] and parts[4] == 'review':
                    return self.send(200, workbench.compliance.review(parts[3], data))
                if len(parts) == 4 and parts[:2] == ['api', 'organizations'] and parts[3] == 'challenge':
                    return self.send(200, workbench.challenge(parts[2], data.get('authorization_reference')))
                self.send(404, {'error': 'Nicht gefunden'})
            except KeyError as ex:
                self.send(404, {'error': str(ex)})
            except RevisionConflict as ex:
                self.send(409, {'error': str(ex)})
            except (ValueError, TypeError) as ex:
                self.send(400, {'error': str(ex)})
            except Exception:
                self.send(500, {'error': 'Interner Fehler; lokale Daten und Serverprotokoll prüfen'})

        def import_csv(self):
            if self.headers.get('Content-Type','').split(';')[0].strip().lower() not in {'text/csv','application/csv'}:
                return self.send(415, {'error':'CSV als text/csv und UTF-8 senden'})
            try:
                size = int(self.headers.get('Content-Length','0'))
                if not 0 < size <= 32 * 1024 * 1024:
                    return self.send(413, {'error':'CSV muss 1 Byte bis 32 MiB groß sein'})
                query = parse_qs(urlsplit(self.path).query)
                filename = query.get('filename',['input.csv'])[0]
                if not 1 <= len(filename) <= 200 or any(c in filename for c in '\r\n\x00'):
                    raise ValueError('Ungültiger Dateiname')
                column = query.get('url_column',[None])[0]
                # Bound memory while accepting the raw upload; no source file overwrite.
                with tempfile.SpooledTemporaryFile(max_size=1024*1024) as source:
                    left = size
                    while left:
                        chunk = self.rfile.read(min(left,65536))
                        if not chunk:
                            raise ValueError('CSV-Upload unvollständig')
                        source.write(chunk)
                        left -= len(chunk)
                    source.seek(0)
                    wrapper = io.TextIOWrapper(source, encoding='utf-8', newline='')
                    try:
                        result = workbench.registry.import_csv(wrapper, filename=filename, url_column=column)
                    finally:
                        wrapper.detach()
                return self.send(201, result)
            except (ValueError, UnicodeError) as ex:
                return self.send(400, {'error':str(ex)})
            except Exception:
                return self.send(500, {'error':'CSV-Import fehlgeschlagen; kein erfolgreicher Import bestätigt'})
    return Handler

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8787)
    parser.add_argument('--storage', default='.runtime')
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(Workbench(args.storage)))
    print(f'Forina local workbench listening on loopback port {server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == '__main__':
    main()
