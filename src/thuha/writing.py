"""Writing support built from the repository alone: the data pack a writer starts from, the draft builder, advisory lint,
fix hints and the readiness ranking.

Everything here is read-only: no ledger write and no WordPress call. Nothing here changes QA. The threshold, the points and
every hard failure stay in `config/qa.json` and `quality.py`; a lint is a warning with a way to fix it, never a score, and a
pack never invents a price, a policy, a source or a media ID: what the repository does not hold is listed as missing.
"""
import copy
import re
import subprocess
from html.parser import HTMLParser
from .common import ROOT, age, fold, load, norm, urlkey, validate_inventory
from .coordinator import claimable, claim_order
from .language import LANGUAGES, TOPIC_ID, locale, topic_language
from .matrix import candidate_shell, matrix_path
from .policy import HTML_POLICY
from .quality import DISCLAIMER
from .research import FIRST_PARTY_FILES, capture_repository_file, evidence_current, item_language
from . import datawait

HEADING = re.compile(r'h[1-6]')


def settings():
    return load(ROOT / 'config/writing.json')


# ------------------------------------------------------------------------------------------------ reading a body

class Blocks(HTMLParser):
    """Paragraph-level view of a body: `blocks` (tag, text), `headings` (level, text), `anchors` (href, text), in order."""
    BLOCK = {'p', 'li', 'td', 'th', 'blockquote', 'figcaption', 'caption'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks, self.headings, self.anchors, self.order = [], [], [], []
        self._open, self._anchor = [], None

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCK or HEADING.fullmatch(tag):
            self._open.append([tag, []])
        elif tag == 'br' and self._open:
            self._open[-1][1].append(' ')
        if tag == 'a':
            self._anchor = [dict(attrs).get('href', ''), []]

    def handle_endtag(self, tag):
        if tag == 'a' and self._anchor:
            self.anchors.append((self._anchor[0], ' '.join(''.join(self._anchor[1]).split())))
            self._anchor = None
        if self._open and self._open[-1][0] == tag:
            name, parts = self._open.pop()
            text = ' '.join(''.join(parts).split())
            if HEADING.fullmatch(name):
                self.headings.append((int(name[1]), text))
                self.order.append(('h', int(name[1]), text))
            elif text:
                self.blocks.append((name, text))
                self.order.append(('b', name, text))

    def handle_data(self, data):
        if self._open:
            self._open[-1][1].append(data)
        if self._anchor:
            self._anchor[1].append(data)


def blocks(html):
    parsed = Blocks()
    parsed.feed(html or '')
    return parsed


def words(text):
    return norm(text).split()


def sentences(text):
    return [s.strip() for s in re.split(r'(?<=[.!?…])\s+', text) if s.strip()]


def stored_bodies(store, state, language, exclude=None, limit=None):
    """Bodies of the stored drafts of one language (for the likeness check). A document that cannot be read is skipped."""
    out = {}
    for tid, submission in sorted(state['submissions'].items()):
        if tid == exclude or state['topics'].get(tid, {}).get('language') != language:
            continue
        try:
            out[tid] = store.get_document(submission['article_sha']).get('body_html', '')
        except (ValueError, OSError, KeyError):
            continue
        if limit and len(out) >= limit:
            break
    return out


# ------------------------------------------------------------------------------------------------ money in the text

def money(text, cfg=None):
    """Amounts written with a currency unit, as integers of dong. A phone number or a year is never read as money."""
    cfg = cfg or settings()
    units = cfg['money']['vi_units']
    found = []
    grouped = r'\d{1,3}(?:[.,]\d{3})+'
    for m in re.finditer(r'(?<![\d.,])(' + grouped + r')\s*(?:-|–|—|đến|to)\s*(' + grouped + r')\s*(?:' + units + r')(?![\w])', text, re.I):
        found += [int(re.sub(r'[.,]', '', m.group(1))), int(re.sub(r'[.,]', '', m.group(2)))]  # "1.000.000-1.200.000 đồng": the unit serves both ends
    for m in re.finditer(r'(?<![\d.,])(' + grouped + r'|\d+)\s*(' + units + r')(?![\w])', text, re.I):
        number = re.sub(r'[.,]', '', m.group(1))
        if re.fullmatch(grouped, m.group(1)) or int(number) >= 1000:
            found.append(int(number))
    for m in re.finditer(r'(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(k|nghìn|ngàn)(?![\w])', text, re.I):
        if float(m.group(1).replace(',', '.')) >= 10 or re.search(r'[.,]', m.group(1)):  # "2K" in "K, 2K" is algebra, not two thousand dong
            found.append(int(round(float(m.group(1).replace(',', '.')) * 1000)))
    for m in re.finditer(r'(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(triệu|tr)(?![\w])', text, re.I):
        found.append(int(round(float(m.group(1).replace(',', '.')) * 1000000)))
    for m in re.finditer(r'(?:VND|₫)\s*(\d{1,3}(?:,\d{3})+)', text):
        found.append(int(m.group(1).replace(',', '')))
    return list(dict.fromkeys(found))


def vnd(value):
    return '{:,}'.format(int(value)).replace(',', '.')


def reference_matches(amount, business):
    """(vehicle, period, 'endpoint'|'inside') for every reference interval the amount belongs to."""
    out = []
    for vehicle, periods in business['reference_prices_vnd'].items():
        for period, interval in periods.items():
            if not interval:
                continue
            if amount in (interval[0], interval[1]):
                out.append((vehicle, period, 'endpoint'))
            elif interval[0] < amount < interval[1]:
                out.append((vehicle, period, 'inside'))
    return out


# ------------------------------------------------------------------------------------------------ business snippets

def contact_html(lang, business, cfg=None):
    """The shop's contact line written from the confirmed facts only: name, hours, address and phone."""
    cfg = cfg or settings()
    hours = re.search(r'(\d\d:\d\d)\D+(\d\d:\d\d)', business['hours'])
    address = business['address']
    if lang == 'en':
        address = address.replace('gần Bến xe Gia Lâm', 'near Gia Lâm bus station')
    digits = re.sub(r'\D', '', business['phone'])
    link = '<a href="tel:+%s">%s</a>' % (digits, business['local_phone'])
    return cfg['contact'][lang].format(name=business['name'], address=address, phone_link=link,
                                       hours_vi=(hours.group(1) + ' đến ' + hours.group(2)) if hours else business['hours'],
                                       hours_en=(hours.group(1) + '–' + hours.group(2)) if hours else business['hours'])


def price_table(business, lang):
    rows = []
    for vehicle, periods in business['reference_prices_vnd'].items():
        for period, interval in periods.items():
            if not interval:
                rows.append({'vehicle': vehicle, 'period': period, 'interval': None, 'text': None, 'note': 'no reference price: never invent one'})
                continue
            low, high = interval
            text = ('%s đồng' % vnd(low)) if low == high else (('từ %s đến %s đồng' % (vnd(low), vnd(high))) if lang == 'vi' else ('%s to %s VND' % (vnd(low), vnd(high))))
            rows.append({'vehicle': vehicle, 'period': period, 'interval': [low, high], 'text': text,
                         'claim_example': {'kind': 'reference_price', 'vehicle': vehicle, 'period': period, 'value_vnd': low}})
    return rows


def nap_markers(business):
    """Fragments that identify a sentence as the shop's contact line (so it is left out of a similarity comparison)."""
    phones = {re.sub(r'\D', '', business['phone']), re.sub(r'\D', '', business['local_phone'])}
    return {'phones': {p for p in phones if p}, 'address': norm(business['address'].split(',')[0])}


def without_contact(text, markers):
    kept = []
    for sentence in sentences(text):
        digits = re.sub(r'\D', '', sentence)
        if any(p in digits for p in markers['phones']) or markers['address'] and markers['address'] in norm(sentence):
            continue
        kept.append(sentence)
    return ' '.join(kept)


# ------------------------------------------------------------------------------------------------ fix hints

def _hint_for(code, table):
    if code in table:
        return table[code]
    best, size = None, -1
    for pattern, hint in table.items():
        if '*' not in pattern:
            continue
        literal = pattern.replace('*', '')
        head, tail = pattern.split('*', 1)
        if code.startswith(head) and code.endswith(tail) and len(literal) > size:
            best, size = hint, len(literal)
    return best


def hints(codes, cfg=None):
    """A place and a way to fix for every failure code, so a writer repairs the text instead of guessing."""
    table = (cfg or settings())['hints']
    out = []
    for code in sorted(set(codes)):
        hint = _hint_for(code, table)
        out.append({'code': code, 'where': (hint or {}).get('where', 'unknown'),
                    'fix': (hint or {}).get('fix', 'Không có gợi ý cho mã này: đọc quality.py để biết điều kiện.')})
    return out


# ------------------------------------------------------------------------------------------------ prices in the text

def _contains(folded, markers):
    return any(fold(m).lower() in folded for m in markers)


def price_findings(parsed, text, article, business, cfg, lang):
    """Judge the amounts a sentence presents as the shop's. QA checks declared claims only, so an undeclared or unapproved price in the prose
    would otherwise pass unseen. A fine, a premium or the arithmetic of a worked example is never a shop price, even when a number happens
    to equal one, so only sentences that name the shop or talk of a rental price per day, week or month are read."""
    spec = cfg['prices']
    claims = [c for c in (article.get('business_claims') or []) if isinstance(c, dict)]
    declared = {c.get('value_vnd') for c in claims}
    policies = {name: keys for name, keys in cfg['readiness']['policy_keywords'].items() if name in business.get('unconfirmed_policies', [])}
    confirmed = {business['extension_policy']['hourly_rate_vnd']} if (business.get('extension_policy') or {}).get('hourly_rate_vnd') else set()  # a fee the owner confirmed
    quoted, unapproved, undeclared, inside, policy_amounts = {}, {}, {}, {}, {}
    for _, block in parsed.blocks:
        for sentence in sentences(block):
            amounts = money(sentence, cfg)
            if not amounts:
                continue
            folded = ' ' + fold(sentence).lower() + ' '
            named = _contains(folded, spec['shop_markers'][lang])
            if not named and not _contains(folded, spec['price_phrases'][lang]):
                continue
            if _contains(folded, spec['hypothetical_markers'][lang]):
                continue  # an illustration says so itself ("ví dụ", "giả sử"): its numbers are the writer's, not the shop's
            for amount in amounts:
                matches = reference_matches(amount, business)
                if named:
                    for name, keys in policies.items():
                        if _contains(folded, keys):
                            policy_amounts.setdefault(amount, name)
                if not matches:
                    if named and amount not in confirmed:
                        unapproved.setdefault(amount, sentence[:120])
                    continue
                quoted.setdefault(amount, sentence[:120])
                if amount not in declared:
                    undeclared.setdefault(amount, [{'vehicle': v, 'period': p} for v, p, kind in matches if kind == 'endpoint'])
                if all(kind == 'inside' for _, _, kind in matches):
                    inside.setdefault(amount, sentence[:120])
    out = []
    listing = lambda values: ', '.join(vnd(a) for a in sorted(values))
    if unapproved:
        out.append(finding('LINT_PRICE_NOT_APPROVED', 'fix', 'A sentence about the shop gives an amount that is not an approved reference price: %s đồng. The shop never gave it.' % listing(unapproved),
                           'Chỉ nêu giá tham khảo đã được chủ cửa hàng xác nhận (xem business.price_table); nếu là ví dụ tính toán thì nói rõ "ví dụ minh họa" trong cùng câu và không gắn với cửa hàng.',
                           amounts=sorted(unapproved)))
    if policy_amounts:
        out.append(finding('LINT_POLICY_AMOUNT', 'fix', 'An amount is tied to a policy the shop has not confirmed (%s): %s đồng.' % (', '.join(sorted(set(policy_amounts.values()))), listing(policy_amounts)),
                           'Bỏ con số: bài chỉ nói nên hỏi cửa hàng điều gì, không nêu mức tiền của chính sách chưa được xác nhận.', amounts=sorted(policy_amounts)))
    if undeclared:
        out.append(finding('LINT_PRICE_NOT_DECLARED', 'consider' if claims else 'fix',
                           'Reference price(s) %s đồng are quoted but %s, so QA cannot check %s.' % (listing(undeclared), 'not every one is declared in business_claims' if claims else 'none is declared in business_claims', 'them' if len(undeclared) > 1 else 'it'),
                           'Khai báo business_claims {"kind":"reference_price","vehicle":...,"period":...,"value_vnd":...} cho từng mức giá cửa hàng nêu trong bài.',
                           amounts=sorted(undeclared), candidates=[c for v in undeclared.values() for c in v]))
    if inside:
        out.append(finding('LINT_PRICE_INSIDE_INTERVAL', 'consider', '%s đồng lies inside a reference interval but is not one of its ends: that is a precision the shop did not state.' % listing(inside),
                           'Nêu cả khoảng giá thay vì một điểm giữa khoảng.', amounts=sorted(inside)))
    if quoted and not re.search(DISCLAIMER[lang], text, re.I):
        out.append(finding('LINT_DISCLAIMER_MISSING', 'fix', 'The text quotes a reference price but never says it is only a reference to confirm before booking.', 'Thêm câu: ' + cfg['disclaimer'][lang]))
    written = set(money(text, cfg))
    for c in sorted(claims, key=str):
        if c.get('value_vnd') not in written:
            out.append(finding('LINT_CLAIM_NOT_IN_TEXT', 'consider', 'business_claims declares %s %s %s but the text never writes that amount.' % (c.get('vehicle'), c.get('period'), c.get('value_vnd')),
                               'Bỏ khai báo thừa hoặc viết con số đó vào bài.'))
    return out


# ------------------------------------------------------------------------------------------------ lint

def finding(code, severity, message, fix, **extra):
    return dict({'code': code, 'severity': severity, 'message': message, 'fix': fix}, **extra)


def shingles(tokens, n):
    return {tuple(tokens[i:i + n]) for i in range(max(0, len(tokens) - n + 1))} or ({tuple(tokens)} if tokens else set())


def jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def similarity(blocks_a, blocks_b, lang, markers, cfg):
    """How much of A repeats B: near-duplicate paragraphs (contact lines left out) and the likeness of the outlines."""
    spec = cfg['similarity']
    n = spec['shingle'][lang]
    paragraphs_b = [shingles(words(without_contact(text, markers)), n) for _, text in blocks_b.blocks]
    paragraphs_b = [p for p in paragraphs_b if p]
    shared = total = 0
    for _, text in blocks_a.blocks:
        tokens = words(without_contact(text, markers))
        total += len(tokens)
        if len(tokens) < n:
            continue
        mine = shingles(tokens, n)
        if any(jaccard(mine, other) >= spec['paragraph_threshold'] for other in paragraphs_b):
            shared += len(tokens)
    heads_a = [set(words(t)) for level, t in blocks_a.headings if level == 2]
    heads_b = [set(words(t)) for level, t in blocks_b.headings if level == 2]
    likeness = (sum(any(jaccard(h, g) >= spec['outline_threshold'] for g in heads_b) for h in heads_a) / len(heads_a)) if heads_a else 0.0
    return {'shared_words': shared, 'total_words': total, 'shared_ratio': round(shared / total, 3) if total else 0.0,
            'outline_likeness': round(likeness, 3), 'outline_headings': len(heads_a)}


def lint(article, topic, business, others=None, cfg=None):
    """Advisory findings about an article. `fix` findings are mechanical or editorial faults QA would not catch; `consider` ones are
    judgement calls. `others` maps topic IDs to the bodies of other stored drafts of the same language (for the likeness check)."""
    cfg = cfg or settings()
    lang = topic['language']
    body = str(article.get('body_html') or '')
    parsed = blocks(body)
    text = ' '.join(t for _, t in parsed.blocks)
    folded = fold(text).lower()
    out = []
    # --- mechanical
    if re.search(cfg['markdown_residue'], body):
        out.append(finding('LINT_MARKDOWN_RESIDUE', 'fix', 'The body still holds Markdown (**bold**, #, a list dash or [text](url)), which WordPress would print as it is.',
                           'Viết bằng HTML: <strong>, <h2>, <ul><li>, <a href>.'))
    levels = [level for level, _ in parsed.headings]
    previous, problems = 1, []  # the page title is the h1; the body starts at h2
    for level, heading in parsed.headings:
        if not heading:
            problems.append('empty heading')
        if level == 1:
            problems.append('h1 in the body')
        elif level > previous + 1:
            problems.append('h%d after h%d' % (level, previous))
        previous = level
    if problems:
        out.append(finding('LINT_HEADING_LEVEL', 'fix', 'Heading levels are broken: ' + '; '.join(sorted(set(problems))) + '.',
                           'Bắt đầu bằng <h2>, <h3> chỉ nằm trong một <h2>, không bỏ cấp và không để tiêu đề rỗng.'))
    if levels.count(2) < cfg['headings']['recommended_min_h2']:
        out.append(finding('LINT_FEW_SECTIONS', 'consider', 'Only %d <h2> sections (QA needs 2; %d or more reads better).' % (levels.count(2), cfg['headings']['recommended_min_h2']),
                           'Chia bài theo các câu hỏi của người đọc, mỗi mục một <h2>.'))
    # --- metadata
    meta = str(article.get('meta_description') or '')
    if len(meta) > cfg['metadata']['meta_description']['recommended_max']:
        out.append(finding('LINT_META_TOO_LONG', 'consider', 'meta_description has %d characters; search results usually cut it near %d.' % (len(meta), cfg['metadata']['meta_description']['recommended_max']),
                           'Rút gọn còn tối đa %d ký tự mà vẫn nêu ý chính.' % cfg['metadata']['meta_description']['recommended_max']))
    keyword = str(article.get('focus_keyword') or topic.get('primary_keyword') or '')
    if keyword and norm(keyword) and norm(keyword) not in norm(text):
        out.append(finding('LINT_KEYWORD_NOT_IN_BODY', 'consider', 'The focus keyword is not found in the body as written.', 'Dùng từ khóa chính một cách tự nhiên trong đoạn mở đầu; không nhồi.'))
    if keyword and norm(keyword) and not any(norm(keyword) in norm(str(article.get(f) or '')) for f in ('title', 'seo_title', 'meta_description')):
        out.append(finding('LINT_KEYWORD_NOT_IN_HEADLINES', 'consider', 'The focus keyword is in none of title, seo_title and meta_description.', 'Đưa từ khóa vào seo_title hoặc meta_description.'))
    # --- anchors
    generic = {fold(x).lower() for x in cfg['anchors']['generic'][lang]}
    for href, label in parsed.anchors:
        if href.startswith(('tel:', 'mailto:', '#')):
            continue
        if fold(label).lower() in generic or len(label.split()) < cfg['anchors']['min_words']:
            out.append(finding('LINT_GENERIC_ANCHOR', 'consider', 'Anchor text "%s" says nothing about the target.' % label, 'Dùng chữ mô tả trang đích (tên bài hoặc chủ đề), ít nhất hai từ.', anchor=label))
            break
    # --- prices: only what a sentence presents as the shop's own is judged, and only against the confirmed reference intervals
    out.extend(price_findings(parsed, text, article, business, cfg, lang))
    # --- provenance leaking into the voice of the shop
    for phrase in cfg['leakage'][lang]:
        if fold(phrase).lower() in folded:
            out.append(finding('LINT_SOURCE_NOTE_LEAK', 'fix', 'The text exposes how it was produced or sourced ("%s").' % phrase,
                               'Viết như người am hiểu nói với người đọc; nguồn đi vào mục sources, không vào giọng văn.', phrase=phrase))
            break
    # --- padding
    seen_sentences, repeated = {}, []
    for sentence in sentences(text):
        key = ' '.join(words(sentence))
        if len(key.split()) >= 8:
            seen_sentences[key] = seen_sentences.get(key, 0) + 1
    repeated = [k for k, v in seen_sentences.items() if v > 1]
    tokens = words(text)
    n = cfg['padding']['shingle']
    grams = [tuple(tokens[i:i + n]) for i in range(max(0, len(tokens) - n + 1))]
    counts = {}
    for g in grams:
        counts[g] = counts.get(g, 0) + 1
    ratio = (sum(1 for g in grams if counts[g] > 1) / len(grams)) if grams else 0.0
    if repeated or ratio > cfg['padding']['repeated_shingle_ratio']:
        out.append(finding('LINT_PADDING', 'fix', 'The text repeats itself (%d repeated sentences, %.0f%% of %d-word phrases occur twice or more).' % (len(repeated), ratio * 100, n),
                           'Bỏ phần lặp; nếu bài ngắn hơn mức tối thiểu thì thêm thông tin có thật, không thêm câu rỗng.', repeated_sentences=len(repeated)))
    long_limit = cfg['length']['long_paragraph_words']
    if any(len(t.split()) > long_limit for _, t in parsed.blocks):
        out.append(finding('LINT_LONG_PARAGRAPH', 'consider', 'A paragraph runs past %d words.' % long_limit, 'Tách thành các đoạn ngắn hoặc dùng danh sách.'))
    # --- likeness to the other stored drafts of the same language
    markers = nap_markers(business)
    spec = cfg['similarity']
    for other_id, other_body in sorted((others or {}).items()):
        report = similarity(parsed, blocks(other_body), lang, markers, cfg)
        structural = report['outline_headings'] >= spec['min_outline_headings'] and report['outline_likeness'] >= spec['outline_threshold']
        if report['shared_ratio'] >= spec['shared_words_fix_ratio'] or structural:
            out.append(finding('LINT_TEMPLATE_SIMILARITY', 'fix', 'Reads like %s: %d of %d words sit in near-duplicate paragraphs and %.0f%% of the section headings match.' % (
                other_id, report['shared_words'], report['total_words'], report['outline_likeness'] * 100),
                'Viết lại theo ý định riêng của chủ đề này: khác cấu trúc mục, khác ví dụ, không dùng lại đoạn của bài khác.', other=other_id, **report))
        elif report['shared_ratio'] >= spec['shared_words_consider_ratio']:
            out.append(finding('LINT_TEMPLATE_SIMILARITY', 'consider', 'Shares %d%% of its words with %s in near-duplicate paragraphs.' % (round(report['shared_ratio'] * 100), other_id),
                               'Xem lại các đoạn trùng.', other=other_id, **report))
    return out


# ------------------------------------------------------------------------------------------------ declaring a wait

def submission_check(result, waiting_for, allow_faults=False):
    """Decide whether a draft may be submitted as it is, and with which exact wait. Returns (ok, problems, waiting_for).

    A draft with a known fault is not submitted (nothing is spent). A draft that depends on data that exists nowhere yet must say
    so: the codes it declares are exactly the ones it needs, plus AUTHORITATIVE_INVENTORY if it likes (an offline inventory is
    always older than QA accepts, so that one is never required). `auto` takes the needed codes from the check.
    """
    problems = []
    needed = [c for c in result.get('data_waits', []) if c not in ('AUTHORITATIVE_INVENTORY', 'FEATURED_MEDIA')]
    faults = list(result.get('content_fails', [])) + [f['code'] for f in result.get('lint', []) if f['severity'] == 'fix']
    if faults and not allow_faults:
        problems.append('Known faults (nothing was submitted, no repair was spent): ' + ', '.join(sorted(set(faults))))
    declared = sorted(set(waiting_for or [])-{'FEATURED_MEDIA'}) # ignore retired wait
    if declared == ['auto']:
        declared = needed
    unknown = [c for c in declared if c not in ('FEATURED_MEDIA', 'INTERNAL_LINKS', 'AUTHORITATIVE_INVENTORY')]
    if unknown:
        problems.append('Unknown wait code: ' + ', '.join(unknown))
    missing = [c for c in needed if c not in declared]
    if missing:
        problems.append('The draft depends on data that does not exist yet; store it with --waiting-for ' + ' '.join(needed) + ' (or auto). Missing: ' + ', '.join(missing))
    extra = [c for c in declared if c not in needed and c != 'AUTHORITATIVE_INVENTORY']
    if extra:
        problems.append('Declared waits that are not needed (the data is there, so the draft is not waiting for it): ' + ', '.join(extra))
    if problems:
        return False, problems, declared
    return True, [], declared


# ------------------------------------------------------------------------------------------------ the data pack

def matrix_row(topic_id, language):
    try:
        rows = load(matrix_path(language))['rows']
    except (OSError, ValueError, KeyError):
        return None
    return next((r for r in rows if r['id'] == topic_id), None)


def git_head():
    try:
        return subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def relevance(topic_words, *texts):
    other = {w for text in texts for w in words(text or '') if len(w) > 2}
    return round(len(topic_words & other) / max(1, len(topic_words)), 3)


def source_status(store, ref, policy):
    """Is a saved source still usable, and for what? Nothing is fetched: only what the repository already holds is judged."""
    out = {'url': ref['url'], 'document': ref['document'], 'supports': ref.get('supports')}
    try:
        evidence = store.get_document(ref['document'])
    except (ValueError, OSError, KeyError):
        return dict(out, current=False, problem='the evidence document is not in the ledger')
    first_party = evidence.get('capture_method') == 'repository-file'
    days = round(age(evidence['checked_at']) / 86400, 1) if evidence.get('checked_at') else None
    current = (evidence.get('url') == ref['url'] and evidence.get('http_status') == 200 and days is not None and 0 <= days * 86400 <= policy['research_max_age_seconds']
               and evidence_current(evidence))
    host = '' if first_party else (re.sub(r'^https?://', '', ref['url']).split('/')[0])
    official = host.endswith(('.gov.vn', '.gov.uk', '.gov', '.gouv.fr')) or host in ('unece.org', 'www.unece.org')
    note = ('first-party: supports statements about the shop only (name, address, hours, reference prices); never an official source for a legal claim' if first_party
            else 'official host: may support a regulated claim' if official else 'external page: the saved capture holds the title and a short excerpt only; read the page again to write facts from it')
    out = dict(out, current=bool(current), age_days=days, kind='first-party' if first_party else 'external', host=host, official=official,
               excerpt_words=len(str(evidence.get('excerpt', '')).split()), note=note)
    if first_party and not current:
        out['problem'] = ('the shop facts file changed or the capture is too old: run `source --repository-file config/business-facts.json` and pass the new '
                          'document in the meta file as extra_sources; `build` leaves this stale one out')
    return out


def expectations(topic, inv, policy):
    """What this topic will wait for given the inventory at hand (a prediction from data, not from the article)."""
    lang = topic['language']
    live = [x for x in inv['items'] if item_language(x) == lang and x.get('public_check', {}).get('http_status') == 200]
    archives = [c for c in inv['categories'] if c.get('language') == lang and c.get('link')]
    waits = []
    if len(live) < policy['minimum_internal_content_links'] or len(live) + len(archives) < policy['minimum_internal_links']:
        waits.append('INTERNAL_LINKS')
    usable = True
    try:
        validate_inventory(inv, policy['inventory_max_age_seconds'])
    except ValueError:
        usable = False
    return {'waits': waits, 'inventory_usable_for_qa': usable, 'live_content_items': len(live), 'category_archives': len(archives),
            'can_complete_without_waiting': not waits}


def pack(store, state, inv, topic_id, policy, business, cfg=None):
    """Everything a writer needs for one topic, assembled from the repository so nobody types it again. Read-only."""
    cfg = cfg or settings()
    admitted = topic_id in state['topics']
    row = None
    if admitted:
        topic = state['topics'][topic_id]
        lang = topic['language']
        row = matrix_row(topic_id, lang)
    else:
        lang = topic_language(topic_id)
        row = matrix_row(topic_id, lang)
        if not row:
            raise ValueError('Unknown topic: neither in the ledger nor in the matrix')
        topic = {'topic_id': row['id'], 'language': lang, 'status': 'MATRIX_ROW', 'proposed_title': row['title'], 'primary_keyword': row['primary_keyword'],
                 'search_intent': row['search_intent'], 'category_id': row['category_id'], 'category_path': row['category_path'],
                 'cluster': (row.get('cluster') or ''), 'proposed_url': row['proposed_url'], 'sources': []}
    keywords = {w for w in words(topic.get('primary_keyword', '') + ' ' + topic.get('search_intent', '') + ' ' + topic.get('proposed_title', '')) if len(w) > 2}
    names = {c['id']: c for c in inv['categories']}
    chain = []
    for index, cid in enumerate(topic['category_path']):
        cat = names.get(cid)
        if cat:
            chain.append({'id': cid, 'name': cat.get('name'), 'slug': cat.get('slug'), 'url': cat.get('link'), 'language': cat.get('language'),
                          'parent': cat.get('parent'), 'source': 'inventory'})
        elif row and index < len(row.get('category_path_names', [])):
            chain.append({'id': cid, 'name': row['category_path_names'][index], 'slug': None, 'url': None, 'language': lang, 'parent': None, 'source': 'matrix'})
    lease = next((l for l in state['leases'].values() if l['topic_id'] == topic_id), None)
    saved = [source_status(store, ref, policy) for ref in topic.get('sources', [])]
    seen = {s['document'] for s in saved}
    library = {}
    for other in state['topics'].values():
        for ref in other.get('sources', []):
            if ref['document'] in seen or ref['document'] in library:
                continue
            try:
                evidence = store.get_document(ref['document'])
            except (ValueError, OSError, KeyError):
                continue
            score = relevance(keywords, evidence.get('page_title', ''), evidence.get('excerpt', ''), ref['url'])
            if score > 0 or evidence.get('capture_method') == 'repository-file':
                library[ref['document']] = dict(source_status(store, ref, policy), relevance=score, used_by=other['topic_id'])
    reusable = sorted((s for s in library.values() if s['current']), key=lambda s: (-s['relevance'], s['url']))[:5]
    live = datawait.link_catalogue(inv, lang)
    for item in live:
        item['relevance'] = relevance(keywords, item.get('title'), item['url'])
    live.sort(key=lambda r: (-r['relevance'], r['type'] != 'posts', r['id']))
    archives = []
    path = list(topic['category_path'])
    for cat in inv['categories']:
        if cat.get('language') == lang and cat.get('link'):
            archives.append({'id': cat['id'], 'name': cat.get('name'), 'url': cat['link'], 'on_topic_path': cat['id'] in path,
                             'relevance': relevance(keywords, cat.get('name'), cat.get('slug'))})
    archives.sort(key=lambda a: (not a['on_topic_path'], -(path.index(a['id']) if a['on_topic_path'] else 0), -a['relevance'], a['id']))  # the leaf category first
    planned, sibling_ids = [], set()
    for link in ((row or {}).get('internal_link_plan') or {}).get('links', []):
        if link.get('role') == 'sibling_topics':
            sibling_ids.update(link.get('row_ids', []))
    for other in state['topics'].values():
        if other['language'] == lang and other['topic_id'] != topic_id and other.get('proposed_url'):
            planned.append({'id': other['topic_id'], 'title': other.get('proposed_title'), 'url': other['proposed_url'], 'status': other['status'],
                            'relevance': relevance(keywords, other.get('proposed_title'), other.get('primary_keyword'))})
    try:
        for matrix in load(matrix_path(lang))['rows']:
            if matrix['id'] != topic_id and matrix['id'] not in state['topics'] and matrix['id'] in sibling_ids:
                planned.append({'id': matrix['id'], 'title': matrix['title'], 'url': matrix['proposed_url'], 'status': 'MATRIX_ROW', 'relevance': 1.0})
    except (OSError, ValueError, KeyError):
        pass
    planned.sort(key=lambda p: (-p['relevance'], p['id']))
    for entry in planned:
        entry.update(live=False, counts_for_qa=False, note='a link target only after it is published and live-verified; a draft that links to it now waits (INTERNAL_LINKS)')
    target = dict((row or {}).get('service_target') or {})
    if target:
        pages = [x for x in inv['items'] if x.get('type') == 'pages' and item_language(x) == lang and x.get('public_check', {}).get('http_status') == 200]
        label = {w for w in words(target.get('label', '')) if len(w) > 2}
        target['candidates'] = [{'id': x['id'], 'title': x.get('title'), 'url': urlkey_slash(x['url'])} for x in pages if label and jaccard(label, {w for w in words(x.get('title', '')) if len(w) > 2}) > 0]
        target['note'] = ('confirmed address' if target.get('url') else
                          'no dedicated live page of this language exists for this service: link the closest live page the pack lists, never guess a slug' if 'NO_DEDICATED' in str(target.get('url_status'))
                          else 'the page exists but its address is not in the repository until an adapter audit lists it; never guess a slug')
    media = datawait.media_catalogue(inv, lang)
    options = sorted(({'id': m['id'], 'alt_text': m['alt_text'], 'source_url': m.get('source_url'), 'relevance': relevance(keywords, m.get('alt_text'), m.get('source_url'))} for m in media),
                     key=lambda m: (-m['relevance'], m['id']))
    expect = expectations(topic, inv, policy)
    unit = 'syllables' if lang == 'vi' else 'words'
    skeleton = None
    if admitted:
        skeleton = {'topic_id': topic_id, 'session': (lease or {}).get('session'), 'agent_id': (lease or {}).get('agent_id'), 'source_commit': git_head(),
                    'language': locale(lang), 'title': topic['proposed_title'], 'body_html': '', 'seo_title': '', 'meta_description': '',
                    'focus_keyword': topic['primary_keyword'], 'canonical': topic['proposed_url'], 'category_id': topic['category_id'], 'featured_media': None,
                    'sources': [{'url': s['url'], 'document': s['document'], 'supports': s['supports']} for s in saved], 'business_claims': []}
    notes = []
    if not options:
        notes.append('Optional media unavailable for %s: leave featured_media null and submit normally; no WordPress image or alt access needed.' % lang)
    if not live:
        notes.append('No live verified page of this language is known: links to category archives and to planned pages are possible, but QA needs at least one live content link.')
    if any(s['kind'] == 'external' and s.get('excerpt_words', 0) <= 20 for s in saved if s.get('kind')):
        notes.append('External sources are saved as a title and a short excerpt only: the facts must come from reading the page again, never from memory.')
    if not admitted:
        notes.append('This topic is a matrix row, not yet admitted to the ledger: there is no lease and no skeleton; the pack is for planning.')
    return {'mode': 'read-only-writing-pack', 'wordpress_writes': 0, 'ledger_writes': 0, 'admitted': admitted, 'language': lang, 'article_language_value': locale(lang),
            'topic': {k: topic.get(k) for k in ('topic_id', 'status', 'proposed_title', 'primary_keyword', 'search_intent', 'cluster', 'proposed_url', 'category_id', 'category_path')},
            'intent_type': (row or {}).get('intent_type'), 'canonical': topic['proposed_url'], 'taxonomy': chain,
            'lease': lease and {k: lease[k] for k in ('slot', 'session', 'agent_id', 'fence', 'expires_at')},
            'business': {'name': business['name'], 'address': business['address'], 'phone': business['phone'], 'local_phone': business['local_phone'], 'hours': business['hours'],
                         'contact_html': contact_html(lang, business, cfg), 'price_table': price_table(business, lang), 'price_disclaimer': cfg['disclaimer'][lang],
                         'extension_policy': business.get('extension_policy'),
                         'never_assert': business['unconfirmed_policies'], 'rules': business['rules']},
            'sources': {'saved': saved, 'reusable': reusable},
            'internal_links': {'live': live, 'archives': archives, 'planned': planned[:10], 'service_target': target or None,
                               'minimum': {'links': policy['minimum_internal_links'], 'content_links': policy['minimum_internal_content_links']}},
            'media': {'options': options, 'note': 'alt text in the article language only; a choice is the writer\'s, nothing is picked here'},
            'template': {'seo_title': cfg['metadata']['seo_title'], 'meta_description': cfg['metadata']['meta_description'],
                         'length': {'unit': unit, 'minimum': policy['substantial_length'][lang]}, 'recommended_min_h2': cfg['headings']['recommended_min_h2'],
                         'html': {'tags': HTML_POLICY['tags'], 'void_tags': HTML_POLICY['void_tags'], 'attributes': HTML_POLICY['attributes'],
                                  'rules': ['no <h1>, no comments, lower-case tags, double-quoted attributes', 'sections are <h2>, <h3> only inside an <h2>']}},
            'existing_titles_same_category': [x['title'] for x in inv['items'] if topic['category_id'] in x.get('categories', [])],
            'expectations': expect, 'skeleton': skeleton, 'notes': notes, 'rules': datawait_rules(lang)}


def urlkey_slash(url):
    return url.rstrip('/') + '/'


def datawait_rules(lang):
    from .runtime import RULES
    return RULES[lang]


# ------------------------------------------------------------------------------------------------ building a draft

def stale_sources(data):
    """The saved sources `compose` leaves out because they are no longer current (the shop facts file changed, or the capture is too old)."""
    return [{'url': s['url'], 'document': s['document'], 'problem': s.get('problem') or 'not current'} for s in data['sources']['saved'] if not s.get('current')]


def price_claims(price_table, specs):
    """`reference_price` claims from 'vehicle:period' shorthands (`"claims": ["manual:month"]` in a meta file): one per end of the
    shop's range, exactly as the pack's price table lists them. A price the facts file lacks is refused, never made up."""
    known = {(p['vehicle'], p['period']): p for p in price_table}
    claims = []
    for spec in specs:
        vehicle, _, period = str(spec).rpartition(':')
        row = known.get((vehicle, period))
        if not row or not row.get('interval'):
            raise ValueError('The shop facts file has no reference price for %r (known: %s); nothing is invented'
                             % (spec, ', '.join(sorted('%s:%s' % key for key, p in known.items() if p.get('interval')))))
        for value in sorted(set(row['interval'])):
            claim = {'kind': 'reference_price', 'vehicle': vehicle, 'period': period, 'value_vnd': value}
            if claim not in claims:
                claims.append(claim)
    return claims


def matrix_candidates(store, ids, cfg=None):
    """Intake candidates for matrix rows that ask for nothing the repository cannot give: the shop's own facts, or no source at all
    (`readiness.first_party_kinds`). The owner facts file is captured as first-party evidence and attached with what it does and does
    not support. A row that needs a manufacturer page, an official page or a field check is refused by name; nothing is guessed."""
    cfg = cfg or settings()
    allowed = set(cfg['readiness']['first_party_kinds'])
    problems, rows = [], []
    for topic_id in ids:
        match = TOPIC_ID.fullmatch(topic_id)
        row = matrix_row(topic_id, match.group(1).lower()) if match else None
        if not match:
            problems.append('%s is not a topic ID (TH-VI-#### or TH-EN-####)' % topic_id)
        elif not row:
            problems.append('%s is not a row of the matrix' % topic_id)
        elif row.get('kind') != 'NEW' or row.get('writer_state') != 'NEEDS_SOURCE':
            problems.append('%s is not a new row waiting for admission (it is %s)' % (topic_id, row.get('kind') or 'unknown'))
        elif [k for k in row.get('source_requirements') or [] if k not in allowed]:
            problems.append('%s needs %s: capture that source first and admit it with --file' % (topic_id, ', '.join(k for k in row['source_requirements'] if k not in allowed)))
        else:
            rows.append(row)
    if problems:
        raise ValueError('; '.join(problems))
    evidence = capture_repository_file(store, FIRST_PARTY_FILES[0])  # after every row passed: a refused batch captures nothing
    candidates = []
    for row in rows:
        candidate = candidate_shell(row)
        candidate.pop('intent_review')  # collisions are checked by intake itself; no reviewer verdict exists
        candidate['cluster'] = row['hub_url'].rstrip('/').split('/')[-1] if row.get('hub_url') else candidate['cluster']
        candidate['sources'] = [{'url': evidence['url'], 'document': evidence['document'], 'supports': cfg['first_party_supports'][row['language']]}]
        candidates.append(candidate)
    return candidates


def compose(data, body_html, meta, session=None, agent_id=None, source_commit=None):
    """An article from the pack's skeleton, a body and a small meta file: nothing the repository already knows is typed again."""
    if not data.get('skeleton'):
        raise ValueError('This topic is not admitted to the ledger, so there is nothing to build for it')
    article = copy.deepcopy(data['skeleton'])
    for key in ('seo_title', 'meta_description'):
        if not str(meta.get(key, '')).strip():
            raise ValueError('The meta file needs ' + key)
    article['session'] = session or article['session']
    article['agent_id'] = agent_id or article['agent_id']
    if not article['session'] or not article['agent_id']:
        raise ValueError('No lease for this topic: claim it first, or pass --session and --agent-id')
    article['source_commit'] = source_commit or article['source_commit'] or git_head()
    if not article['source_commit']:
        raise ValueError('source_commit is unknown: run inside the repository checkout')
    article['title'] = str(meta.get('title') or article['title']).strip()
    article['seo_title'] = str(meta['seo_title']).strip()
    article['meta_description'] = str(meta['meta_description']).strip()
    media = meta.get('featured_media')
    if media is not None and media not in {m['id'] for m in data['media']['options']}:
        raise ValueError('featured_media %r is not one of the verified options for this language; nothing is invented' % (media,))
    article['featured_media'] = media
    claims = list(meta.get('business_claims', []))
    claims += [c for c in price_claims(data['business']['price_table'], meta.get('claims', [])) if c not in claims]
    article['business_claims'] = claims
    current = {s['document'] for s in data['sources']['saved'] if s.get('current')}
    sources = [s for s in article['sources'] if s['document'] in current]  # a stale capture is a certain QA fault
    for extra in meta.get('extra_sources', []):  # the skeleton already holds the saved first-party source: it is not listed twice
        if not any((s['url'], s['document']) == (extra.get('url'), extra.get('document')) for s in sources):
            sources.append(extra)
    article['sources'] = sources
    article['body_html'] = str(body_html).strip()
    return article


# ------------------------------------------------------------------------------------------------ what to write next

def wordset(*texts):
    return {w for text in texts for w in words(text or '') if len(w) > 2}


def overlap_of(topic_words, candidates):
    """The most similar other title or keyword set: (score, id). Jaccard of word sets, so it is the same measure everywhere."""
    best = (0.0, None)
    for ident, other in candidates:
        score = jaccard(topic_words, other)
        if score > best[0]:
            best = (round(score, 3), ident)
    return best


def policy_flags(text, business, cfg):
    """Policies the shop has not confirmed that the topic is about: the article may say what to ask, never what the policy is."""
    folded = fold(text).lower()
    return sorted(name for name, keys in cfg['readiness']['policy_keywords'].items()
                  if name in business.get('unconfirmed_policies', []) and any(fold(k).lower() in folded for k in keys))


def stale_first_party(store, state, language=None):
    """Stored drafts whose first-party evidence the shop facts file has outgrown. They cannot pass QA until the evidence is captured again
    (`source --repository-file`) and the draft is submitted with the fresh capture; a HELD draft is only counted, because it is not submitted."""
    active, held = [], 0
    for tid, submission in sorted(state['submissions'].items()):
        topic = state['topics'].get(tid, {})
        if (language and topic.get('language') != language) or topic.get('status') in ('PUBLISHED', 'PUBLISHING'):
            continue
        try:
            article = store.get_document(submission['article_sha'])
            outgrown = any(evidence.get('capture_method') == 'repository-file' and not evidence_current(evidence)
                           for evidence in (store.get_document(ref['document']) for ref in article.get('sources', [])))
        except (ValueError, OSError, KeyError):
            continue
        if outgrown and topic.get('status') == 'HELD':
            held += 1
        elif outgrown:
            active.append({'topic_id': tid, 'status': topic.get('status')})
    return {'needs_recapture': active, 'held_not_resubmitted': held}


def _cycles(edges):
    """Groups of more than one topic that reach each other through `edges` (strongly connected components, iterative Tarjan)."""
    index, low, stack, on, groups, counter = {}, {}, [], set(), [], [0]

    def enter(node):
        index[node] = low[node] = counter[0]
        counter[0] += 1
        stack.append(node)
        on.add(node)
        return (node, iter(edges.get(node, ())))

    for root in sorted(set(edges) | {t for targets in edges.values() for t in targets}):
        if root in index:
            continue
        work = [enter(root)]
        while work:
            node, children = work[-1]
            for child in children:
                if child not in index:
                    work.append(enter(child))
                    break
                if child in on:
                    low[node] = min(low[node], index[child])
            else:
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[node])
                if low[node] == index[node]:
                    group = []
                    while True:
                        member = stack.pop()
                        on.discard(member)
                        group.append(member)
                        if member == node:
                            break
                    if len(group) > 1:
                        groups.append(sorted(group))
    return sorted(groups)


def link_graph(store, state, language=None, replace=None):
    """The links stored drafts make to the planned (not yet live) address of another topic, and the cycles those links form.

    QA refuses a link to a page that is not live, and a draft whose only fault is such a link waits (BLOCKED_DATA) until the page is
    live. A draft can therefore pass only after every topic it links to is published, and drafts that link to each other, directly or
    through others, can never pass: none of them can be first. `replace` maps a topic ID to an article that is not stored yet.
    """
    by_url = {urlkey(t['proposed_url']): tid for tid, t in state['topics'].items() if t.get('proposed_url') and (not language or t['language'] == language)}
    pending = lambda tid: state['topics'][tid]['status'] not in ('PUBLISHED', 'PUBLISHING')
    articles = {}
    for tid, submission in state['submissions'].items():
        topic = state['topics'].get(tid)
        if not topic or (language and topic['language'] != language) or not pending(tid):
            continue
        try:
            articles[tid] = store.get_document(submission['article_sha'])
        except (ValueError, OSError, KeyError):
            continue
    for tid, article in (replace or {}).items():
        if tid in state['topics']:
            articles[tid] = article
    edges = {}
    for tid, article in sorted(articles.items()):
        targets = sorted(t for t in {by_url[k] for k in datawait.own_links(article, state['topics'][tid]) if k in by_url} if t != tid and pending(t))
        if targets:
            edges[tid] = targets
    return {'depends_on': edges, 'cycles': _cycles(edges)}


def readiness(store, state, inv, policy, business, language=None, limit=10, cfg=None):
    """What can be written now, in order. Read-only; nothing is claimed, admitted or written.

    Vietnamese first. A HELD topic is never offered: a hold ends only when whoever resolved its cause lifts it. A topic that needs an
    official or manufacturer page nobody has read is not offered as writable (no fact is written from memory); a matrix row that
    asks only for the shop's own facts or no source at all can be admitted.
    """
    cfg = cfg or settings()
    spec = cfg['readiness']
    first_party = set(spec['first_party_kinds'])
    languages = [language] if language else list(LANGUAGES)
    start, admit, blocked = [], [], {}
    held = sum(1 for t in state['topics'].values() if t['status'] == 'HELD' and (not language or t['language'] == language))
    for lang in languages:
        expect = expectations({'language': lang}, inv, policy)
        titles = [(x['id'], wordset(x.get('title'), x.get('slug'))) for x in inv['items'] if item_language(x) == lang]
        in_ledger = {tid: t for tid, t in state['topics'].items() if t['language'] == lang}
        others = [(tid, wordset(t.get('proposed_title'), t.get('primary_keyword'))) for tid, t in in_ledger.items()]
        rows = {}
        try:
            rows = {r['id']: r for r in load(matrix_path(lang))['rows']}
        except (OSError, ValueError, KeyError):
            pass
        planned_rows = [(rid, wordset(r.get('title'), r.get('primary_keyword'))) for rid, r in rows.items() if r.get('kind') == 'NEW' and rid not in in_ledger]
        busy = {l['topic_id'] for l in state['leases'].values()}

        def judge(topic_id, title, keyword, intent, kinds, saved_current, status, admitted):
            own = wordset(title, keyword)
            # an unadmitted row is also compared with the other unadmitted rows: two rows that ask the same question are one topic
            score, nearest = overlap_of(own, [c for c in others if c[0] != topic_id] + titles + ([c for c in planned_rows if c[0] != topic_id] if not admitted else []))
            policies = policy_flags(' '.join((title or '', keyword or '', intent or '')), business, cfg)
            external = [k for k in kinds if k not in first_party]
            reasons, label = [], 'START' if not expect['waits'] else 'START_STORE_WAITING'
            if external and not saved_current:
                label = 'NEEDS_SOURCE'
                reasons.append('needs %s: no saved page of that kind is current, and a fact is never written from memory' % ', '.join(external))
            elif external:
                label = 'READ_SOURCE_FIRST'
                reasons.append('saved external sources hold a title and a short excerpt: read the page again before writing a fact from it')
            if score >= spec['overlap_threshold']:
                label = 'CHECK_OVERLAP'
                reasons.append('close to %s (%.2f): decide that it adds an intent of its own before writing' % (nearest, score))
            if policies:
                reasons.append('about an unconfirmed policy (%s): say what to ask the shop, never what the policy is' % ', '.join(policies))
            if label in ('START_STORE_WAITING', 'READ_SOURCE_FIRST') and expect['waits']:
                reasons.append('will be stored waiting for ' + ' and '.join(expect['waits']))
            if not admitted and label in ('START', 'START_STORE_WAITING'):
                label = 'ADMIT_FIRST'
                reasons.append('not in the ledger: capture the shop facts as first-party evidence, then intake')
            return {'topic_id': topic_id, 'language': lang, 'title': title, 'status': status, 'readiness': label, 'reasons': reasons,
                    'waits_expected': expect['waits'], 'source_kinds': kinds, 'overlap': {'score': score, 'with': nearest}, 'policy_flags': policies}

        for tid, topic in sorted(in_ledger.items(), key=lambda kv: claim_order(kv[1])):
            if topic['status'] == 'HELD' or not claimable(topic) or tid in busy:
                continue
            row = rows.get(tid) or {}
            saved = [source_status(store, ref, policy) for ref in topic.get('sources', [])]
            current_external = any(s.get('current') and s.get('kind') == 'external' for s in saved)
            kinds = list(row.get('source_requirements') or ([] if all(s.get('kind') == 'first-party' for s in saved) else ['external_page']))
            item = judge(tid, topic.get('proposed_title'), topic.get('primary_keyword'), topic.get('search_intent'), kinds, current_external, topic['status'], True)
            (start if item['readiness'] != 'NEEDS_SOURCE' else blocked.setdefault('NEEDS_SOURCE', [])).append(item)
        for rid, row in sorted(rows.items(), key=lambda kv: kv[1].get('write_order', 0)):
            if row['kind'] != 'NEW' or rid in in_ledger:
                continue
            kinds = list(row.get('source_requirements') or [])
            if any(k not in first_party for k in kinds):
                blocked.setdefault('NEEDS_SOURCE', []).append({'topic_id': rid, 'language': lang, 'readiness': 'NEEDS_SOURCE', 'source_kinds': kinds})
                continue
            admit.append(judge(rid, row['title'], row['primary_keyword'], row['search_intent'], kinds, False, 'MATRIX_ROW', False))
    rank = {'START': 0, 'START_STORE_WAITING': 1, 'ADMIT_FIRST': 2, 'READ_SOURCE_FIRST': 3, 'CHECK_OVERLAP': 4}
    order = lambda items: sorted(items, key=lambda i: (LANGUAGES.index(i['language']), rank[i['readiness']], len(i['reasons']), i['topic_id']))
    return {'mode': 'read-only-next', 'wordpress_writes': 0, 'ledger_writes': 0,
            'order': 'Vietnamese first; inside a language: finish without waiting, store waiting, admit from the matrix, read a saved source again, and last the topics that overlap another',
            'inventory': {'language_source': inv.get('language_source'), 'captured_at': inv.get('captured_at')},
            'start_now': order(start)[:limit], 'admit_first': order(admit)[:limit],
            'not_writable_here': {k: len(v) for k, v in blocked.items()}, 'held_not_offered': held,
            'stale_first_party_evidence': stale_first_party(store, state, language),
            'planned_link_cycles': link_graph(store, state, language)['cycles']}
