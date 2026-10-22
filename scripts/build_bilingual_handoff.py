"""Build reference-only topic extracts and taxonomy planning views. No network/writes to WP."""
import csv
import html
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/bilingual'
SOURCE = ROOT.parent / 'wp-aiwriter'


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    cats = json.loads((OUT / 'live-categories-2026-10-22.json').read_text())['categories']
    by_id = {c['id']: c for c in cats}
    children = {c['parent'] for c in cats}
    vi_alloc = {152:30,153:30,154:25,155:25,156:30,157:30,158:20,
                159:25,160:25,161:25,162:25,163:30,164:30,165:30,
                166:25,167:25,168:25,169:15,170:15,171:15}
    # New EN additions, not quotas for the legacy posts already in their categories.
    en_alloc = {123:15,124:15,125:15,126:10,141:20,142:15,143:10,
                129:10,130:15,131:10,132:10,133:10,134:10,144:15,145:10,
                135:10,136:5,137:10,138:5,139:5}
    assert sum(vi_alloc.values()) == 500
    assert sum(en_alloc.values()) == 225

    def ancestors(c):
        chain, seen = [c], {c['id']}
        while chain[0]['parent']:
            p = by_id[chain[0]['parent']]
            assert p['id'] not in seen
            seen.add(p['id'])
            chain.insert(0, p)
        return chain

    rows = []
    for c in sorted(cats, key=lambda x: x['id']):
        chain = ancestors(c)
        assert all(x['language'] == c['language'] for x in chain)
        rows.append({'language':c['language'], 'id':c['id'], 'parent':c['parent'],
                     'name':html.unescape(c['name']), 'slug':c['slug'], 'url':c['link'],
                     'category_path':' > '.join(html.unescape(x['name']) for x in chain),
                     'ancestor_ids':','.join(str(x['id']) for x in chain[:-1]),
                     'role':'excluded' if c['id']==1 else ('hub' if c['id'] in children else 'leaf'),
                     'suggested_new_topics':vi_alloc.get(c['id'], en_alloc.get(c['id'], 0)),
                     'published_direct_count_at_capture':c['count']})
    with (OUT / 'taxonomy-map.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    save('plan.json', {'site':'https://rentbikehanoi.com','schema_version':1,
        'status':'TAXONOMY_PROVISIONED_WORKFLOW_MIGRATION_PENDING',
        'final_published_post_targets':{'vi':500,'en':500},
        'snapshot_published_posts':{'vi':0,'en':275},
        'snapshot_missing_posts':{'vi':500,'en':225}, 'priority':['vi','en'],
        'counting':'Distinct published post IDs by native language; pages excluded; reconcile live before reservation.',
        'allocation_policy':'Editorial suggestion only. Rebalance after intent dedup and source checks; never fill with near-duplicates.',
        'suggested_vi_new_topics_by_category':vi_alloc,
        'suggested_en_new_topics_by_category':en_alloc,
        'production_publishing_enabled':False,
        'native_vi_adapter_status':'NOT_IMPLEMENTED_NOT_DEPLOYED',
        'sitemap_pairs_only':False,
        'categories_total':len(cats), 'new_categories':49,
        'vi_categories':27,'new_en_categories':22})
    if not (SOURCE / 'en/topics.json').exists():
        en = json.loads((OUT / 'reference-en-ideas.json').read_text())['ideas']
        vi = json.loads((OUT / 'reference-vi-ideas.json').read_text())['ideas']
        assert len(en)==500 and len(vi)==355
        assert len(cats)==59 and len(by_id)==59
        assert sum(c['language']=='vi' for c in cats)==27
        print('Validated bundled handoff without requiring another repository: 59 categories; 500 VI +225 EN allocations.')
        return
    commit = subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
    en = json.loads((SOURCE / 'en/topics.json').read_text())
    vi = json.loads((SOURCE / 'data/topics.json').read_text())
    save('reference-en-ideas.json', {'source_repository':'thuexemayhanoi/wp-aiwriter',
        'source_commit':commit, 'source_file':'en/topics.json','status':'IDEAS_ONLY_NOT_APPROVED_NOT_PUBLISHED',
        'do_not_import':'Source category IDs, slugs, URLs, ledger, prose and business facts are not target configuration.',
        'ideas':[{'reference_key':f"wpai-en-{r['id']}",'title':r['title'],
                  'intent':r.get('intent'),'keywords':r.get('keywords',[])} for r in en]})
    save('reference-vi-ideas.json', {'source_repository':'thuexemayhanoi/wp-aiwriter',
        'source_commit':commit, 'source_file':'data/topics.json',
        'status':'IDEAS_ONLY_NOT_APPROVED_NOT_PUBLISHED',
        'coverage':'355 explicit rows, IDs 146–500. Missing legacy 1–145 is not reconstructed.',
        'ideas':[{'reference_key':f'wpai-vi-{r[0]}','title':r[1], 'reference_category_path':r[2]} for r in vi]})
    assert len(en)==500 and len(vi)==355
    assert len(cats)==59 and len(by_id)==59
    assert sum(c['language']=='vi' for c in cats)==27
    print('Validated: 59 categories; VI allocation500; EN additions225; source ideas500EN/355VI.')


if __name__ == '__main__':
    main()
