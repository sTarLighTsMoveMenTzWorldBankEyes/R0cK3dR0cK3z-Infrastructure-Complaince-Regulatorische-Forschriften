"""Build a portable, provenance-preserving source catalog from onboarding inventory."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
ROLES = [
    ('AI-PACT', 'Security & Policy', 'Dienste, OPA-Regeln, Code Doctor und Ledger'),
    ('guardrails', 'Regulatory Policy', 'Offline-Prüfplanung und Domain-Challenge-Entwürfe'),
    ('Hnoss', 'Governance', 'Next.js-Oberfläche und Governance-Architektur'),
    ('Corpus', 'Relationship Graph', 'React-Oberfläche und Beziehungsmodell'),
    ('BIRDHOW', 'Infrastructure', 'Infrastrukturkonzept'),
    ('DSGVO', 'Rights Framework', 'Datenschutz, Menschenrechte und KI-Ethik'),
    ('IHoLy', 'Finance & Identity', 'Finanz- und Identitätskonzept'),
    ('CaZaR', 'Institutional Context', 'Institutionelle Architekturkonzepte'),
    ('INTERMEDIALGALAKTICConst', 'Ethical Governance', 'Governance- und Werteentwürfe'),
    ('DACH', 'Values', 'Gesellschaftliches Leitbild'),
    ('LoveAeTHer', 'Ethical Principles', 'Gemeinschafts- und Ethikkonzept'),
]

def build(inventory):
    projects = []
    documents = []
    for row in inventory:
        source = Path(row['path'])
        role = next((r for key, *r in ROLES if key in row['archive']), ['Context', 'Quellenbestand'])
        project_id = row['sha256'][:16]
        files = []
        for path in sorted(source.rglob('*')):
            if not path.is_file() or '__pycache__' in path.parts:
                continue
            raw = path.read_bytes()
            rel = path.relative_to(source).as_posix()
            item = {'path': rel, 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
            files.append(item)
            if path.suffix.lower() in {'.md', '.txt', '.rego', '.yaml', '.yml', '.py', '.json', '.ts', '.tsx', '.js', '.rs', '.html', '.sh'}:
                try:
                    content = raw.decode('utf-8')
                except UnicodeDecodeError:
                    continue
                # Bounded text excerpts; complete originals remain in uploaded archives.
                documents.append({'project_id': project_id, 'path': rel, 'sha256': item['sha256'], 'text': content[:24000], 'truncated': len(content) > 24000})
        projects.append({'id': project_id, 'archive': row['archive'], 'archive_sha256': row['sha256'], 'role': role[0], 'description': role[1], 'files': files, 'file_count': len(files), 'integration': 'Guardrails adapter' if 'guardrails' in row['archive'] else 'Source catalog', 'verified': False})
    return {'schema_version': 1, 'projects': projects, 'documents': documents}

if __name__ == '__main__':
    inventory = json.loads(Path(sys.argv[1]).read_text())
    catalog = build(inventory)
    (ROOT / 'forina/data/catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, separators=(',', ':')))
    print(f"Imported {len(catalog['projects'])} archives, {sum(p['file_count'] for p in catalog['projects'])} files, {len(catalog['documents'])} text excerpts")
