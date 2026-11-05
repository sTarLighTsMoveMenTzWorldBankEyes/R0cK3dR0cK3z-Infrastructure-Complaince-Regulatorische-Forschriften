"""Ingest project-context documents through the existing local intake mechanism."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from forina.core import Workbench

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage', type=Path, default=ROOT / '.runtime')
    args = parser.parse_args()
    register = Workbench(args.storage).compliance
    for name in ('FORINA_CONCEPT_V1.md', 'LOVABLE_ANALYSIS_USER_PROVIDED.md', 'CSV_AUTH_ARCHITECTURE.md'):
        body = {'title': name, 'content': (ROOT / 'docs' / name).read_text()}
        preview = register.preview(body)
        result = register.ingest_document({**body, 'preview_digest':preview['preview_digest'], 'expected_digest':preview['replaces_digest']})
        print(json.dumps({'document':name, **result}, ensure_ascii=False))

if __name__ == '__main__':
    main()
