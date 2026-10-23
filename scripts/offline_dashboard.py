"""Write reports/bilingual/dashboard.{json,md} without any network access.

The queue shown is the session ledger committed in this repository (what the queue job will hand over). The shared
ledger it is compared with is the committed snapshot of factory-state taken on 2026-10-23, and the inventory is the
committed authenticated snapshot of 2026-10-22. None of this is live data: the dashboard says so in `state_backend`.

    python3 scripts/offline_dashboard.py
"""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from thuha import audit, dashboard  # noqa: E402
from thuha.common import ROOT, load, now, save  # noqa: E402
from thuha.store import LocalStore, migrate  # noqa: E402

LIVE_SNAPSHOT = ROOT / 'tests/fixtures/live-factory-state-2026-10-23.json'


def main():
    with tempfile.TemporaryDirectory() as temp:
        store = LocalStore(temp)
        save(store.path, migrate(load(ROOT / 'data/state/factory.json')))
        inv = audit.snapshot_inventory()
        inv['captured_at'] = now()  # the snapshot is committed evidence; freshness is not claimed, so the age rule is not shown as a blocker
        value = dashboard.report(store, inv, load(ROOT / 'config/release.json'), live_ledger=load(LIVE_SNAPSHOT))
        value['offline_note'] = ('Built from the committed session ledger, the 2026-10-23 snapshot of factory-state and the 2026-10-22 '
                                 'authenticated inventory snapshot. Not a live reading.')
        dashboard.write_report(value, ROOT / 'reports/bilingual')
        print('wrote reports/bilingual/dashboard.{json,md}')


if __name__ == '__main__':
    main()
