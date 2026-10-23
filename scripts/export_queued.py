"""Write data/bilingual/existing-queued-en.json from the session ledger.

Topics already admitted to the ledger (researched, sourced) are not published posts and do not count toward 500
until WordPress confirms them, but the English matrix must neither re-plan nor collide with them. Only the legacy
`TH-######` topics are queued work outside the matrix; a `TH-EN-####` topic IS a matrix row and is not exported.

    python3 scripts/export_queued.py [--ledger data/state/factory.json]
"""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from thuha.common import ROOT, digest, load, save  # noqa: E402
from thuha.language import LEGACY_TOPIC_ID, split_url  # noqa: E402
from thuha.store import migrate  # noqa: E402


def export(ledger_path):
    state = migrate(load(ledger_path))
    topics = []
    for tid, topic in sorted(state['topics'].items()):
        if topic['language'] != 'en':
            continue  # Vietnamese topics are planned in the VI matrix
        if not LEGACY_TOPIC_ID.fullmatch(tid):
            continue  # a TH-EN-#### topic was admitted from a row of the English matrix itself: that row stays a NEW row, as the Vietnamese ones do
        topics.append({'topic_id': tid, 'language': 'en', 'title': topic['proposed_title'], 'slug': split_url(topic['proposed_url'])[1],
                       'url': topic['proposed_url'], 'primary_keyword': topic['primary_keyword'], 'category_id': topic['category_id'],
                       'ledger_status': topic['status']})
    return {'source': 'session ledger ' + str(ledger_path) + ', schema ' + str(state['schema']) + ', version ' + str(state['version']),
            'ledger_events_sha256': digest(state['events'][:-1]) if state['events'] else None,
            'status': 'QUEUED_NOT_PUBLISHED',
            'note': 'English topics already admitted to the ledger with captured sources. They are not published posts and do not count '
                    'toward 500 until WordPress confirms them; the English matrix counts them as planned and never re-plans them.',
            'topics': topics}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--ledger', default='data/state/factory.json')
    args = parser.parse_args()
    value = export(ROOT / args.ledger)
    save(ROOT / 'data/bilingual/existing-queued-en.json', value)
    print(json.dumps({'queued_topics': len(value['topics'])}))
