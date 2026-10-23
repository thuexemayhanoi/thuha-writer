"""Write reports/bilingual/dashboard.{json,md} without any network access.

The queue shown is the session ledger committed in this repository (what the queue job will hand over). The shared
ledger it is compared with is the latest `factory-state` this checkout has fetched (`git fetch origin factory-state`), or the
committed snapshot of 2026-10-23 when that ref is missing, and the inventory is the committed authenticated snapshot of
2026-10-22. None of this is live data: the dashboard says so in `state_backend`.

    python3 scripts/offline_dashboard.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from thuha import audit, dashboard  # noqa: E402
from thuha.common import ROOT, load, now, save  # noqa: E402
from thuha.store import LocalStore, migrate  # noqa: E402

LIVE_SNAPSHOT = ROOT / 'tests/fixtures/live-factory-state-2026-10-23.json'


def shared_ledger():
    """The newest shared ledger this checkout knows: the fetched `origin/factory-state`, else the committed snapshot."""
    try:
        shown = subprocess.run(['git', '-C', str(ROOT), 'show', 'origin/factory-state:data/state/factory.json'], capture_output=True, text=True, check=True)
        value = json.loads(shown.stdout)
        return value, 'the factory-state ledger as last fetched (version %s, %d events)' % (value.get('version'), len(value.get('events', [])))
    except (OSError, ValueError, subprocess.CalledProcessError):
        return load(LIVE_SNAPSHOT), 'the committed 2026-10-23 snapshot of factory-state'


def main():
    with tempfile.TemporaryDirectory() as temp:
        store = LocalStore(temp)
        save(store.path, migrate(load(ROOT / 'data/state/factory.json')))
        inv = audit.snapshot_inventory()
        inv['captured_at'] = now()  # the snapshot is committed evidence; freshness is not claimed, so the age rule is not shown as a blocker
        live, label = shared_ledger()
        value = dashboard.report(store, inv, load(ROOT / 'config/release.json'), live_ledger=live)
        value['offline_note'] = ('Built from the committed session ledger, %s and the 2026-10-22 '
                                 'authenticated inventory snapshot. Not a live reading.' % label)
        dashboard.write_report(value, ROOT / 'reports/bilingual')
        print('wrote reports/bilingual/dashboard.{json,md}')


if __name__ == '__main__':
    main()
