"""Inspect full original text files, validate catalog hashes, emit portable intake package."""
import json
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from forina.intake import TEXT_NAMES, TEXT_SUFFIXES, encoded, extract_document, fingerprint, merge_materials

ROOT = Path(__file__).resolve().parents[1]

def build(inventory, catalog):
    definitions = json.loads((ROOT / 'forina/vendor/guardrails/laws.json').read_text())
    projects = {p['archive_sha256']: p for p in catalog['projects']}
    materials, coverage = [], []
    for row in inventory:
        project = projects[row['sha256']]
        root = Path(row['path']).resolve()
        for entry in project['files']:
            path = (root / entry['path']).resolve()
            if not path.is_relative_to(root):
                raise ValueError('Quellpfad außerhalb des Archivs')
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != entry['sha256']:
                raise ValueError('Geänderte Archivquelle: ' + entry['path'])
            item = {'project_id': project['id'], 'path': entry['path'], 'sha256': entry['sha256'], 'status': 'NON_TEXT_NOT_INTERPRETED'}
            if any(part in {'.npm-cache', 'node_modules', '__pycache__', '.git'} for part in path.relative_to(root).parts):
                item['status'] = 'DEPENDENCY_OR_BUILD_CACHE'
            elif path.suffix.lower() in TEXT_SUFFIXES or path.name in TEXT_NAMES:
                try:
                    content = raw.decode('utf-8')
                except UnicodeDecodeError:
                    item['status'] = 'DECODE_NOT_SUPPORTED'
                else:
                    materials.append(extract_document(entry['path'], content, project['archive'], definitions, project['id']))
                    item['status'] = 'FULL_TEXT_EXTRACTED'
            coverage.append(item)
    package = {'id': 'archive-compliance', 'schema_version': 1, **merge_materials(materials), 'coverage': coverage,
        'network_access': 'NONE', 'legal_verification': 'NOT_PERFORMED'}
    package['digest'] = fingerprint(package)
    return package

if __name__ == '__main__':
    catalog = json.loads((ROOT / 'forina/data/catalog.json').read_text())
    package = build(json.loads(Path(sys.argv[1]).read_text()), catalog)
    (ROOT / 'forina/data/compliance.json').write_bytes(encoded(package))
    print(json.dumps({'documents': len(package['documents']), 'links': len(package['links']), 'candidates': len(package['candidates']), 'files_accounted_for': len(package['coverage']), 'digest': package['digest']}))
