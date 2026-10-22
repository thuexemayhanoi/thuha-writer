"""Editorial matrices: 500 Vietnamese posts first, then the English gap to 500.

Rows are PLANNED topics, never published posts and never source evidence. Every NEW
row starts at `NEEDS_SOURCE`: the factory still demands captured, dated sources and
an independent intent review before a topic is admitted, and none of that can be
produced offline. Existing English posts appear only as EXISTING_PROTECTED rows so
the English total is auditable; they are never rewritten, retitled or reparented.

Seeds (data/bilingual/seeds/*.jsonl) hold the hand-written topic ideas; `build`
expands them with the real category IDs and URLs from the committed manifest.
"""
import csv
import html
import json
import re
import sys
from pathlib import Path
from .common import ROOT, SITE, digest, fold, load, norm, save
from .language import LANGUAGES, SLUG, check, post_url, screen, targets as language_targets

DATA = ROOT / 'data/bilingual'
SEEDS = DATA / 'seeds'
MATRIX = DATA / 'matrix'
SNAPSHOT = '2026-10-22'
INTENT_TYPES = ('informational', 'commercial_investigation', 'comparison', 'transactional_support',
                'troubleshooting', 'planning', 'local_navigation')
SOURCE_KINDS = ('first_party_facts', 'official_vn_law', 'official_weather', 'official_health', 'official_venue',
                'official_transport', 'manufacturer_manual', 'field_check', 'editorial_only')
WRITER_STATES = ('NEEDS_SOURCE', 'SOURCE_CAPTURED', 'INTAKE_READY', 'CLAIMED', 'DRAFT_READY',
                 'NEEDS_REPAIR', 'READY', 'VERIFIED', 'BLOCKED')
# Thresholds on content-token overlap (see `similarity`); calibrated on the committed data.
TITLE_FAIL, KEYWORD_FAIL, INTENT_FAIL, TEMPLATE_FAIL, EXISTING_FAIL = 0.6, 0.75, 0.6, 0.8, 0.55
MAX_STEM_FAMILY = 3

STOP = {
    'vi': set('thue xe may ha noi la co khong cho va cua nhung mot cac nen can gi nao the de khi o tai tu den voi ve '
              'se da duoc bao nhieu nhu ra vao tren duoi theo hay hoac neu thi bi minh ban toi nguoi di lam sao'.split()),
    'en': set('a an the and or of to in on at for with by from is are be can do does how what when where which why you '
              'your before after hanoi motorbike motorcycle rental rent scooter bike vietnam it its as if not'.split()),
}
PLACES = ['ba dinh', 'hoan kiem', 'tay ho', 'long bien', 'cau giay', 'dong da', 'hai ba trung', 'hoang mai',
          'thanh xuan', 'nam tu liem', 'bac tu liem', 'ha dong', 'gia lam', 'soc son', 'dong anh', 'me linh',
          'thanh tri', 'my dinh', 'bo de', 'phuc loi', 'viet hung', 'ngoc lam', 'ngoc thuy', 'gia thuy',
          'old quarter', 'pho co', 'tam dao', 'ba vi', 'ninh binh', 'mai chau', 'ha long', 'sapa', 'ha giang',
          'hai phong', 'hoa binh', 'bat trang', 'duong lam', 'co loa', 'dong mo', 'ho tay']
MODELS = ['air blade', 'airblade', 'sh mode', 'wave alpha', 'winner x', 'vision', 'lead', 'sirius', 'exciter',
          'janus', 'vario', 'click', 'future', 'blade', 'klara', 'feliz', 'evo', 'vinfast', 'yadea', 'dibao',
          'mio', 'jupiter', 'satria', 'raider', 'pcx', 'nvx', 'grande', 'luvias', 'freego', 'latte', 'wave',
          'winner', 'cub', 'dream', 'sh', 'ex']
PRICE = re.compile(r'\d[\d.,]*\s*(?:k|nghin|ngan|trieu|vnd|dong|usd|d)\b|\$\s*\d|\b(?:vnd|usd)\b|\d\s*%')
CLAIM = re.compile(r'\b(?:re nhat|tot nhat|so 1|dam bao|bao dam|mien coc|khong can dat coc|khong dat coc|'
                   r'no deposit|deposit free|cheapest|guaranteed|best price)\b')


# --- reference data ---------------------------------------------------------

def taxonomy():
    cats = {c['id']: c for c in load(DATA / 'live-categories-2026-10-22.json')['categories']}
    parents = {c['parent'] for c in cats.values()}
    out = {}
    for cid, c in cats.items():
        chain, seen = [c], {cid}
        while chain[0]['parent']:
            up = cats[chain[0]['parent']]
            if up['id'] in seen:
                raise ValueError('Cyclic taxonomy')
            seen.add(up['id'])
            chain.insert(0, up)
        out[cid] = {'id': cid, 'language': c['language'], 'parent': c['parent'], 'slug': c['slug'], 'url': c['link'],
                    'name': html.unescape(c['name']), 'path_ids': [x['id'] for x in chain],
                    'path_names': [html.unescape(x['name']) for x in chain],
                    'role': 'excluded' if cid == 1 else ('hub' if cid in parents else 'leaf'),
                    'description': c.get('description', '')}
    return out


def plan():
    return load(DATA / 'plan.json')


def services():
    return load(DATA / 'service-targets.json')['keys']


def existing():
    """Everything a new row must not collide with: live EN posts, static pages, queued legacy topics."""
    posts = [{'id': p['id'], 'slug': p['slug'], 'url': p['link'], 'title': html.unescape(p['title']['rendered']),
              'categories': p['categories'], 'kind': 'post'}
             for p in load(DATA / 'live-posts-2026-10-22.json')['posts']]
    pages = load(DATA / 'static-pages.json')
    queued = [{'id': t['topic_id'], 'slug': t['slug'], 'url': t['url'], 'title': t['title'], 'kind': 'queued'}
              for t in load(DATA / 'existing-queued-en.json')['topics']]
    return {'posts': posts, 'pages': [dict(x, kind='page', title=x['slug'].replace('-', ' ')) for x in pages['pages']],
            'queued': queued, 'reserved': set(pages['reserved_slugs'])}


# --- similarity -------------------------------------------------------------

def content_tokens(lang, text):
    return [t for t in norm(text).split() if t not in STOP[lang] and len(t) > 1]


def shingles(lang, text):
    tokens = content_tokens(lang, text)
    return set(tokens) | set(zip(tokens, tokens[1:]))


def similarity(lang, a, b):
    sa, sb = shingles(lang, a), shingles(lang, b)
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


def collapse(lang, title):
    """Title with places and bike models replaced, to expose doorway-style template variants."""
    text = ' ' + norm(title) + ' '
    for word in sorted(PLACES, key=len, reverse=True):
        text = text.replace(' ' + word + ' ', ' PLACE ')
    for word in sorted(MODELS, key=len, reverse=True):
        text = text.replace(' ' + word + ' ', ' MODEL ')
    return ' '.join(t for t in text.split() if t not in STOP[lang])


# --- seeds -> rows ----------------------------------------------------------

def read_seeds(paths):
    rows = []
    for path in paths:
        for number, line in enumerate(Path(path).read_text(encoding='utf-8').splitlines(), 1):
            if line.strip() and not line.lstrip().startswith('#'):
                seed = json.loads(line)
                seed['_at'] = Path(path).name + ':' + str(number)
                rows.append(seed)
    return rows


def seed_files(lang):
    return sorted(SEEDS.glob(lang + '-*.jsonl'))


def expand(seed, lang, tax, svc):
    cat = tax[seed['c']]
    key = seed['s']
    target = {'key': key, 'label': svc[key]['label_' + lang], 'scope': svc[key]['scope']}
    if lang == 'en':
        target.update(url=svc[key]['en_url'], url_status='LIVE_IN_SNAPSHOT_2026-10-22')
    else:
        target.update(url=svc[key]['vi_url'], url_status=svc[key]['vi_url_status'])
    hub = tax[cat['parent']]
    return {
        'language': lang, 'kind': 'NEW', 'category_id': cat['id'], 'category_path': cat['path_ids'],
        'category_path_names': cat['path_names'], 'category_url': cat['url'],
        'hub_category_id': hub['id'], 'hub_url': hub['url'],
        'title': seed['t'], 'primary_keyword': seed['k'], 'search_intent': seed['q'], 'intent_type': seed['i'],
        'slug': seed['u'], 'proposed_url': post_url(lang, seed['u']),
        'service_target': target, 'source_requirements': list(seed['r']), 'priority': seed['p'],
        'demand_evidence': 'NOT_MEASURED',
    }


def finish(rows, lang, tax):
    """IDs, write order, sibling link plan, dedup evidence and writer state for NEW rows."""
    prefix = 'TH-' + lang.upper() + '-'
    order = {int(cid): i for i, cid in enumerate(plan()['suggested_' + lang + '_new_topics_by_category'])}
    rows.sort(key=lambda r: (order[r['category_id']], r['_index']))
    for n, row in enumerate(rows, 1):
        row['id'] = prefix + format(n, '04d')
    ranked = sorted(rows, key=lambda r: (r['priority'], order[r['category_id']], r['_index']))
    for n, row in enumerate(ranked, 1):
        row['write_order'] = n
    by_cat = {}
    for row in rows:
        by_cat.setdefault(row['category_id'], []).append(row)
    ex = existing()
    old = ex['posts'] + ex['pages'] + ex['queued']
    for row in rows:
        mates = sorted((m for m in by_cat[row['category_id']] if m is not row),
                       key=lambda m: -similarity(lang, row['title'] + ' ' + row['search_intent'], m['title'] + ' ' + m['search_intent']))
        siblings = [m['id'] for m in mates if similarity(lang, row['title'], m['title']) < TITLE_FAIL][:3]
        row['internal_link_plan'] = {
            'minimum_internal_links': 2,
            'links': [
                {'role': 'hub_archive', 'url': row['hub_url'], 'status': 'CATEGORY_EXISTS_PER_MANIFEST'},
                {'role': 'leaf_archive', 'url': row['category_url'], 'status': 'CATEGORY_EXISTS_PER_MANIFEST'},
                {'role': 'service', 'key': row['service_target']['key'], 'url': row['service_target']['url'],
                 'status': row['service_target']['url_status']},
                {'role': 'sibling_topics', 'row_ids': siblings, 'status': 'LINK_ONLY_AFTER_PUBLISHED_AND_LIVE_VERIFIED'}],
            'rule': 'QA accepts only same-language URLs verified live in the publisher inventory.'}
        if lang == 'en':
            best = max(((similarity('en', row['title'], o['title']), o) for o in old), key=lambda x: x[0])
            nearest = {'id': best[1]['id'], 'url': best[1]['url'], 'kind': best[1]['kind'], 'score': round(best[0], 3)}
        else:
            nearest = None  # No Vietnamese post exists; the 11 VI pages are unlisted (see static-pages.json).
        others = [(similarity(lang, row['title'], m['title']), m) for m in rows if m is not row]
        top = max(others, key=lambda x: x[0]) if others else (0.0, {'id': None})
        row['dedup'] = {'status': 'OFFLINE_DISTINCT_PENDING_LIVE_RECHECK', 'snapshot': SNAPSHOT,
                        'nearest_existing': nearest, 'nearest_new_row': {'id': top[1]['id'], 'score': round(top[0], 3)},
                        'live_recheck': 'PENDING', 'vi_static_pages_checked': lang == 'en'}
        row['writer_state'] = 'NEEDS_SOURCE'
        row['checkpoint'] = None
        row['next_action'] = 'Capture dated primary sources, then submit for independent intent review and intake.'
        del row['_index']
    return rows


def existing_rows():
    tax = taxonomy()
    rows = []
    for p in load(DATA / 'live-posts-2026-10-22.json')['posts']:
        rows.append({'id': 'WP-EN-' + str(p['id']), 'language': 'en', 'kind': 'EXISTING_PROTECTED', 'wp_id': p['id'],
                     'slug': p['slug'], 'proposed_url': p['link'], 'title': html.unescape(p['title']['rendered']),
                     'category_ids': p['categories'], 'protection': 'NO_EDIT_DELETE_RETITLE_REPARENT_OR_CANONICAL_CHANGE',
                     'source': 'data/bilingual/live-posts-2026-10-22.json'})
    return rows


def build(lang, paths=None):
    check(lang)
    tax, svc = taxonomy(), services()
    seeds = read_seeds(paths or seed_files(lang))
    rows = []
    for index, seed in enumerate(seeds):
        row = expand(seed, lang, tax, svc)
        row['_index'] = index
        rows.append(row)
    rows = finish(rows, lang, tax)
    targets = language_targets()
    snapshot = plan()['snapshot_published_posts'][lang]
    kept = existing_rows() if lang == 'en' else []
    return {
        'schema_version': 1, 'site': SITE, 'language': lang, 'status': 'MATRIX_NOT_PUBLISHED_ARTICLES',
        'snapshot': SNAPSHOT, 'target_total': targets[lang], 'snapshot_published': snapshot,
        'new_rows_expected': targets[lang] - snapshot,
        'counting': 'Rows are planned topics. Only a read-back WordPress post counts toward the target.',
        'rows': kept + rows,
    }


# --- validation -------------------------------------------------------------

def problem(code, row, detail=''):
    return {'code': code, 'row': row.get('id') or row.get('_at'), 'detail': detail}


def check_rows(rows, lang, complete=False, tax=None, svc=None, allowed_categories=None):
    """Return problems for NEW rows (dicts as produced by `expand`, id optional)."""
    tax, svc, ex = tax or taxonomy(), svc or services(), existing()
    out, seen = [], {k: {} for k in ('slug', 'url', 'keyword', 'title', 'intent')}
    slugs = {x['slug'] for x in ex['posts'] + ex['pages'] + ex['queued']} | ex['reserved']
    old_titles = [(x, x['title']) for x in ex['posts'] + ex['queued']]
    collapsed = {}
    stems = {}
    for row in rows:
        at = row.get('id') or row.get('_at')
        cat = tax.get(row.get('category_id'))
        if not cat or cat['language'] != lang or cat['role'] != 'leaf':
            out.append(problem('CATEGORY_NOT_A_LEAF_OF_LANGUAGE', row, str(row.get('category_id'))))
            continue
        if allowed_categories is not None and cat['id'] not in allowed_categories:
            out.append(problem('CATEGORY_OUTSIDE_ASSIGNED_SCOPE', row, str(cat['id'])))
        if row['intent_type'] not in INTENT_TYPES or row['priority'] not in (1, 2, 3):
            out.append(problem('INTENT_TYPE_OR_PRIORITY_INVALID', row))
        if row['service_target']['key'] not in svc:
            out.append(problem('SERVICE_TARGET_UNKNOWN', row))
        if not row['source_requirements'] or any(s not in SOURCE_KINDS for s in row['source_requirements']):
            out.append(problem('SOURCE_REQUIREMENT_INVALID', row))
        if not SLUG.fullmatch(row['slug']) or not 8 <= len(row['slug']) <= 90:
            out.append(problem('SLUG_FORMAT', row, row['slug']))
        if row['slug'] in slugs:
            out.append(problem('SLUG_COLLIDES_WITH_EXISTING_OR_RESERVED', row, row['slug']))
        try:
            if row['proposed_url'] != post_url(lang, row['slug']):
                out.append(problem('URL_NAMESPACE', row, row['proposed_url']))
        except ValueError:
            out.append(problem('URL_NAMESPACE', row, row['proposed_url']))
        for name, value, low, high in (('title', row['title'], 25, 120), ('keyword', row['primary_keyword'], 6, 80),
                                       ('intent', row['search_intent'], 40, 400)):
            if not low <= len(value) <= high:
                out.append(problem('FIELD_LENGTH_' + name.upper(), row, str(len(value))))
            key = norm(value)
            if seen[name].setdefault(key, at) != at:
                out.append(problem('DUPLICATE_' + name.upper(), row, 'same as ' + str(seen[name][key])))
            if screen(lang, value, short=True):
                out.append(problem('WRONG_LANGUAGE_' + name.upper(), row, ','.join(screen(lang, value, short=True))))
        if seen['slug'].setdefault(row['slug'], at) != at:
            out.append(problem('DUPLICATE_SLUG', row))
        text = norm(row['title'] + ' ' + row['primary_keyword'])
        if PRICE.search(fold(row['title'] + ' ' + row['primary_keyword']).lower()) or CLAIM.search(text):
            out.append(problem('UNVERIFIABLE_PRICE_OR_CLAIM_IN_TITLE_OR_KEYWORD', row, row['title']))
        form = collapse(lang, row['title'])
        if collapsed.setdefault(form, at) != at:
            out.append(problem('TEMPLATE_VARIANT_OF_ANOTHER_ROW', row, 'collapsed title equals ' + str(collapsed[form])))
        stem = ' '.join(form.split()[:3])
        stems.setdefault(stem, []).append(at)
        if lang == 'en':
            score, near = max(((similarity('en', row['title'], t), x) for x, t in old_titles), key=lambda pair: pair[0]) if old_titles else (0, None)
            kscore = max((similarity('en', row['primary_keyword'], t) for _, t in old_titles), default=0)
            if score >= EXISTING_FAIL or kscore >= KEYWORD_FAIL:
                out.append(problem('TOO_CLOSE_TO_EXISTING_POST', row, str(near['id']) + ' ' + near['url']))
    for stem, ids in stems.items():
        if stem and len(ids) > MAX_STEM_FAMILY and stem.count('PLACE') + stem.count('MODEL') > 0:
            out.append({'code': 'DOORWAY_STEM_FAMILY_TOO_LARGE', 'row': ids[0], 'detail': stem + ' x' + str(len(ids))})
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if similarity(lang, a['title'], b['title']) >= TITLE_FAIL:
                out.append(problem('TITLES_TOO_SIMILAR', a, str(b.get('id') or b.get('_at'))))
            elif similarity(lang, a['primary_keyword'], b['primary_keyword']) >= KEYWORD_FAIL:
                out.append(problem('KEYWORDS_TOO_SIMILAR', a, str(b.get('id') or b.get('_at'))))
            elif similarity(lang, a['search_intent'], b['search_intent']) >= INTENT_FAIL and a['category_id'] == b['category_id']:
                out.append(problem('INTENTS_TOO_SIMILAR', a, str(b.get('id') or b.get('_at'))))
            elif similarity(lang, collapse(lang, a['title']), collapse(lang, b['title'])) >= TEMPLATE_FAIL:
                out.append(problem('TEMPLATE_VARIANT_OF_ANOTHER_ROW', a, str(b.get('id') or b.get('_at'))))
    return out


def validate(matrix, lang=None):
    """Full acceptance of a built matrix: totals, taxonomy, URLs, allocation, dedup, honesty of state."""
    lang = check(lang or matrix['language'])
    tax, targets, p = taxonomy(), language_targets(), plan()
    rows = matrix['rows']
    out = []
    new = [r for r in rows if r['kind'] == 'NEW']
    kept = [r for r in rows if r['kind'] == 'EXISTING_PROTECTED']
    snapshot = p['snapshot_published_posts'][lang]
    if len(kept) != snapshot or len(new) != targets[lang] - snapshot or len(kept) + len(new) != targets[lang]:
        out.append({'code': 'ROW_COUNT', 'row': None, 'detail': 'protected=%d new=%d target=%d snapshot=%d' % (
            len(kept), len(new), targets[lang], snapshot)})
    if lang == 'en':
        wanted = {x['id'] for x in existing()['posts']}
        if {r['wp_id'] for r in kept} != wanted:
            out.append({'code': 'EXISTING_POSTS_NOT_EXACTLY_PROTECTED', 'row': None, 'detail': 'WordPress IDs differ from snapshot'})
    ids = [r['id'] for r in rows]
    if len(set(ids)) != len(ids):
        out.append({'code': 'DUPLICATE_ID', 'row': None, 'detail': ''})
    for r in new:
        if not re.fullmatch('TH-' + lang.upper() + r'-\d{4}', r['id']):
            out.append(problem('ID_FORMAT', r))
        if r['writer_state'] not in WRITER_STATES or r['writer_state'] != 'NEEDS_SOURCE' or r['checkpoint'] is not None:
            out.append(problem('STATE_CLAIMS_PROGRESS_WITHOUT_EVIDENCE', r))
        if r['dedup']['live_recheck'] != 'PENDING':
            out.append(problem('LIVE_RECHECK_MUST_BE_PENDING', r))
        if tax[r['category_id']]['url'] != r['category_url'] or tax[r['category_id']]['path_ids'] != r['category_path']:
            out.append(problem('CATEGORY_MANIFEST_MISMATCH', r))
        if len(r['internal_link_plan']['links']) < 3:
            out.append(problem('INTERNAL_LINK_PLAN_THIN', r))
    out.extend(check_rows(new, lang, tax=tax))
    planned = {int(k): v for k, v in p['suggested_' + lang + '_new_topics_by_category'].items()}
    counts = {}
    for r in new:
        counts[r['category_id']] = counts.get(r['category_id'], 0) + 1
    for cid, want in planned.items():
        have = counts.get(cid, 0)
        if abs(have - want) > max(3, round(want * 0.2)):
            out.append({'code': 'ALLOCATION_FAR_FROM_PLAN', 'row': None, 'detail': 'category %d planned %d actual %d' % (cid, want, have)})
    for cid in set(counts) - set(planned):
        out.append({'code': 'CATEGORY_NOT_IN_PLAN', 'row': None, 'detail': str(cid)})
    return out


# --- io ---------------------------------------------------------------------

def matrix_path(lang):
    return MATRIX / (lang + '500.json')


def write(lang, matrix):
    save(matrix_path(lang), matrix)
    fields = ['id', 'kind', 'language', 'category_id', 'category_path_names', 'title', 'primary_keyword', 'search_intent',
              'intent_type', 'proposed_url', 'service_target', 'source_requirements', 'priority', 'write_order',
              'writer_state', 'wp_id']
    with (MATRIX / (matrix_path(lang).stem + '.csv')).open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        for r in matrix['rows']:
            flat = dict(r)
            flat['category_path_names'] = ' > '.join(r.get('category_path_names', []))
            flat['service_target'] = r.get('service_target', {}).get('key', '')
            flat['source_requirements'] = '|'.join(r.get('source_requirements', []))
            w.writerow(flat)


def summary(matrix):
    rows = matrix['rows']
    return {'language': matrix['language'], 'rows': len(rows), 'new': sum(r['kind'] == 'NEW' for r in rows),
            'protected': sum(r['kind'] == 'EXISTING_PROTECTED' for r in rows),
            'sha256': digest(matrix)}


def candidate_shell(row):
    """Intake-contract fields a matrix row can fill; sources and intent_review stay empty on purpose."""
    return {'topic_id': row['id'], 'language': row['language'], 'primary_keyword': row['primary_keyword'],
            'search_intent': row['search_intent'], 'proposed_title': row['title'], 'category_id': row['category_id'],
            'category_path': row['category_path'], 'cluster': str(row['category_path'][-1]),
            'proposed_url': row['proposed_url'], 'sources': [], 'intent_review': None}


def main(argv=None):
    """python -m thuha.matrix check FILE... --language vi|en  |  build | validate"""
    argv = list(sys.argv[1:] if argv is None else argv)
    command = argv.pop(0) if argv else 'validate'
    lang = None
    if '--language' in argv:
        i = argv.index('--language')
        lang = argv[i + 1]
        del argv[i:i + 2]
    scope = None
    if '--categories' in argv:
        i = argv.index('--categories')
        scope = {int(x) for x in argv[i + 1].split(',')}
        del argv[i:i + 2]
    if command == 'check':
        # Fast loop for authors: validates seed files only; counts are checked by `validate`.
        # `--against FILE...` adds other seed files to the similarity checks and reports only
        # problems that involve a row of the checked file(s).
        against = []
        if '--against' in argv:
            i = argv.index('--against')
            against = argv[i + 1:]
            argv = argv[:i]
        tax, svc = taxonomy(), services()

        def load_rows(paths):
            out = []
            for seed in read_seeds(paths):
                missing = [k for k in ('c', 't', 'k', 'q', 'i', 's', 'r', 'p', 'u') if k not in seed]
                if missing:
                    raise SystemExit(json.dumps({'code': 'SEED_FIELDS_MISSING', 'row': seed['_at'], 'detail': missing}, ensure_ascii=False))
                row = expand(seed, check(lang), tax, svc)
                row['_at'] = seed['_at']
                out.append(row)
            return out
        mine_files = {Path(x).name for x in argv}
        rows = load_rows(argv)
        others = load_rows([x for x in against if Path(x).name not in mine_files])
        problems = check_rows(others + rows, lang, tax=tax, svc=svc, allowed_categories=scope)
        mine = {r['_at'] for r in rows}
        problems = [p for p in problems if p['row'] in mine or p['detail'] in mine]
        by_cat = {}
        for r in rows:
            by_cat[r['category_id']] = by_cat.get(r['category_id'], 0) + 1
        print(json.dumps({'rows': len(rows), 'per_category': by_cat, 'compared_with_other_rows': len(others), 'problems': problems}, ensure_ascii=False, indent=1))
        return 1 if problems else 0
    langs = [lang] if lang else list(LANGUAGES)
    code = 0
    for l in langs:
        if command == 'build':
            m = build(l)
            write(l, m)
            print(json.dumps(summary(m)))
        problems = validate(load(matrix_path(l)), l)
        print(json.dumps({'language': l, 'problems': problems}, ensure_ascii=False, indent=1))
        code = code or (1 if problems else 0)
    return code


if __name__ == '__main__':
    sys.exit(main())
