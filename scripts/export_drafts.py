"""Write drafts/<language>/<TOPIC>.json and drafts/INDEX.md from the session ledger (data/state/factory.json).

    python3 scripts/export_drafts.py [--ledger data/state/factory.json] [--documents data/documents] [--out drafts]
"""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from thuha.common import ROOT, load  # noqa: E402
from thuha import drafts  # noqa: E402
from thuha.store import migrate  # noqa: E402


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--ledger', default='data/state/factory.json')
    parser.add_argument('--documents', default='data/documents')
    parser.add_argument('--out', default='drafts')
    args = parser.parse_args()
    state = migrate(load(ROOT / args.ledger))
    docs = ROOT / args.documents

    def get_document(sha):
        return json.loads((docs / (sha + '.json')).read_text(encoding='utf-8'))

    written = drafts.export(state, get_document, ROOT / args.out)
    print(json.dumps({'exported': len(written), 'directory': args.out}))
