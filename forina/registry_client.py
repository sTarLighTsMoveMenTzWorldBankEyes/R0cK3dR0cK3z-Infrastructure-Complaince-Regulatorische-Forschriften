"""Offline CSV import/export for the Domain & Compliance Master Registry."""
import argparse
import json
from pathlib import Path

from .core import Workbench

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage', type=Path, default=Path('.runtime'))
    commands = parser.add_subparsers(dest='command', required=True)
    ingest = commands.add_parser('import')
    ingest.add_argument('source', type=Path)
    ingest.add_argument('--url-column', help='Exact CSV header to use instead of automatic detection')
    export = commands.add_parser('export')
    export.add_argument('--output', required=True, type=Path)
    commands.add_parser('summary')
    args = parser.parse_args()
    registry = Workbench(args.storage).registry
    if args.command == 'import':
        with args.source.open(encoding='utf-8', newline='') as source:
            report = registry.import_csv(source, filename=args.source.name, url_column=args.url_column)
        print(json.dumps(report,ensure_ascii=False,indent=2))
    elif args.command == 'export':
        with args.output.open('x',encoding='utf-8',newline='') as target:
            target.write(registry.export_csv())
        print(json.dumps({'exported':str(args.output),'network_access':'NONE'}))
    else:
        print(json.dumps(registry.summary(),ensure_ascii=False,indent=2))

if __name__ == '__main__':
    main()
