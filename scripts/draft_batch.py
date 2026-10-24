#!/usr/bin/env python3
"""Claim, build and store a folder of finished article bodies (see src/thuha/batch.py).

    python3 scripts/draft_batch.py --folder drafts-in/ --ids TH-EN-0011 TH-EN-0025 --session my-session --agent-id my-writer \\
        -- --git-branch --inventory /path/to/inventory.json

`FOLDER/<TOPIC_ID>.html` is the body and `<TOPIC_ID>.json` the meta file (`--meta-folder` to keep them apart). Add `--dry-run` to build
and precheck without claiming anything or writing the ledger. Everything after `--` is passed to `python3 -m thuha.cli` before each
command (`--git-branch`, `--state-dir DIR`, `--inventory FILE`, ...). A draft that is not ready is reported with what to fix and its
lease is released; the run goes on. Exit code 0: every draft was stored (or would be); 2: some draft is not ready; 1: the run stopped.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from thuha.batch import BatchStop, draft_batch  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--folder', required=True, help='folder with <TOPIC_ID>.html bodies (and <TOPIC_ID>.json meta files)')
    parser.add_argument('--ids', nargs='+', required=True, help='topic IDs, stored in this order')
    parser.add_argument('--session', default='batch-session', help='session name of the lease (the identity the drafts are written under)')
    parser.add_argument('--agent-id', default='batch-writer')
    parser.add_argument('--meta-folder', help='folder with the meta files when they are not next to the bodies')
    parser.add_argument('--out-folder', help='keep the built article files here (default: a temporary folder; the ledger keeps what is submitted)')
    parser.add_argument('--dry-run', action='store_true', help='build and precheck only: no claim, no ledger write')
    argv = sys.argv[1:] if argv is None else list(argv)
    split = argv.index('--') if '--' in argv else len(argv)  # argparse's REMAINDER would also swallow this script's own options
    args = parser.parse_args(argv[:split])
    flags = argv[split + 1:]
    env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'))

    def run(*cli_args):
        proc = subprocess.run([sys.executable, '-m', 'thuha.cli', *flags, *cli_args], capture_output=True, text=True, cwd=ROOT, env=env)
        try:
            return proc.returncode, json.loads(proc.stdout)
        except ValueError:
            return proc.returncode, {'raw_stdout': proc.stdout[-2000:], 'stderr': proc.stderr[-2000:]}

    try:
        results = draft_batch(run, args.folder, args.ids, args.session, args.agent_id, args.meta_folder, args.out_folder, args.dry_run,
                              log=lambda m: print(m, file=sys.stderr))
    except BatchStop as stop:
        print(json.dumps({'status': 'STOPPED', 'reason': stop.args[0], 'done': stop.args[1]}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({'status': 'DONE', 'dry_run': args.dry_run, 'results': results}, ensure_ascii=False, indent=2))
    return 2 if any(r['result'] == 'NOT_READY' for r in results) else 0


if __name__ == '__main__':
    sys.exit(main())
