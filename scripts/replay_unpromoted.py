#!/usr/bin/env python3
"""Submit again the drafts that `sync --apply --discard-unpromoted` listed (see src/thuha/replay.py).

    python3 -m thuha.cli --git-branch sync --apply --discard-unpromoted > plan.json
    python3 scripts/replay_unpromoted.py plan.json -- --git-branch

Everything after `--` is passed to `python3 -m thuha.cli` before each command (for example `--git-branch` or `--state-dir DIR`,
and `--inventory FILE` when admission needs an authoritative inventory the ledger does not hold). `--only` limits the topics;
`--override DIR` submits `DIR/<TOPIC_ID>.json` (a rewritten article) instead of the stored document for those topics.
The script stops at the first refusal after releasing its lease and prints what it did as JSON; exit code 1 means it stopped.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from thuha.replay import ReplayStop, replay  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('plan', help='JSON printed by `sync --apply --discard-unpromoted` (or its "unpromoted" block)')
    parser.add_argument('--only', nargs='*', default=[], help='topic IDs to submit again (default: every listed draft)')
    parser.add_argument('--override', help='folder with <TOPIC_ID>.json articles submitted instead of the stored documents')
    parser.add_argument('--documents', default=str(ROOT / 'data/documents'), help='folder of immutable documents (default: the session branch)')
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

    overrides = {p.stem: p for p in Path(args.override).glob('*.json')} if args.override else {}
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    try:
        results = replay(run, plan, args.documents, only=set(args.only), overrides=overrides, log=lambda m: print(m, file=sys.stderr))
    except ReplayStop as stop:
        print(json.dumps({'status': 'STOPPED', 'reason': stop.args[0], 'done': stop.args[1]}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({'status': 'DONE', 'results': results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
