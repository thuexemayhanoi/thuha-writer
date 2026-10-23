"""Import the latest complete inventory document from factory-state into the
session branch's git-branch store, so claim/QA/admission keep a fresh (<6h)
inventory while REST writes are closed. Read-only toward factory-state.

Usage: PYTHONPATH=src python3 scripts/import_inventory.py [--wait-run RUN_ID]
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from thuha.common import digest, validate_inventory  # noqa: E402
from thuha.store import GitBranchStore  # noqa: E402


def git(*args):
    return subprocess.run(['git', '-C', str(ROOT), *args], check=True, capture_output=True, text=True).stdout


def wait_run(run_id):
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('THUHA_GITHUB_TOKEN')
    url = 'https://api.github.com/repos/thuexemayhanoi/thuha-writer/actions/runs/' + str(run_id)
    for _ in range(80):
        req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json', 'User-Agent': 'ThuHa-Writer/5'})
        with urllib.request.urlopen(req, timeout=25) as r:
            run = json.load(r)
        if run['status'] == 'completed':
            return run['conclusion']
        time.sleep(15)
    raise SystemExit('audit run did not complete in time')


def main():
    if '--wait-run' in sys.argv:
        conclusion = wait_run(sys.argv[sys.argv.index('--wait-run') + 1])
        if conclusion != 'success':
            raise SystemExit('audit run concluded ' + str(conclusion) + '; inventory not imported')
    git('fetch', '-q', 'origin', 'factory-state')
    remote_state = json.loads(git('show', 'origin/factory-state:data/state/factory.json'))
    sha = remote_state.get('inventory_document')
    if not sha:
        raise SystemExit('factory-state has no inventory document')
    raw = git('show', 'origin/factory-state:data/documents/' + sha + '.json')
    inv = json.loads(raw)
    if digest(inv) != sha:
        raise SystemExit('factory-state inventory document does not match its address')
    validate_inventory(inv)
    store = GitBranchStore()
    current = store.read().get('inventory_document')
    if current == sha:
        print(json.dumps({'imported': False, 'inventory_document': sha, 'captured_at': inv['captured_at']}))
        return
    store.put_document(inv)
    store.mutate(lambda s: s.update(inventory_document=sha))
    print(json.dumps({'imported': True, 'inventory_document': sha, 'captured_at': inv['captured_at'], 'posts': inv['counts']['posts']}))


if __name__ == '__main__':
    main()
