"""The committed matrices and the rules that keep them honest (no network, no WordPress)."""
import copy
import unittest
from collections import Counter
from thuha import matrix
from thuha.common import SITE, load
from thuha.language import post_url, split_url
from thuha.research import validate_candidate
from thuha.store import LocalStore


def seed(**over):
    base = {'c': 152, 't': 'Ngân sách thuê xe máy một ngày gồm những khoản nào', 'k': 'ngân sách thuê xe một ngày',
            'q': 'Người thuê lần đầu muốn biết ngoài tiền thuê còn những khoản nào cần dự trù để không bị bất ngờ.',
            'i': 'commercial_investigation', 's': 'prices', 'r': ['first_party_facts'], 'p': 1, 'u': 'ngan-sach-thue-xe-mot-ngay-gom-khoan-nao'}
    base.update(over)
    return base


def rows_for(lang, seeds):
    tax, svc = matrix.taxonomy(), matrix.services()
    out = []
    for i, s in enumerate(seeds):
        r = matrix.expand(s, lang, tax, svc);r['_at'] = 'test:%d' % i;out.append(r)
    return out


def codes(lang, seeds):
    return {p['code'] for p in matrix.check_rows(rows_for(lang, seeds), lang)}


class CommittedMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = {l: load(matrix.matrix_path(l)) for l in ('vi', 'en')}
        cls.tax = matrix.taxonomy()
        cls.plan = matrix.plan()

    def test_both_matrices_pass_full_validation(self):
        for lang, m in self.m.items():
            self.assertEqual(matrix.validate(m, lang), [], lang)

    def test_they_are_exactly_what_the_seeds_build(self):
        for lang, m in self.m.items():
            self.assertEqual(matrix.build(lang), m, lang + ' matrix is stale; run scripts/build_matrices.py')

    def test_vietnamese_has_500_new_rows_and_english_275_protected_plus_225_new(self):
        vi, en = self.m['vi']['rows'], self.m['en']['rows']
        self.assertEqual(Counter(r['kind'] for r in vi), {'NEW': 500})
        self.assertEqual(Counter(r['kind'] for r in en), {'EXISTING_PROTECTED': 275, 'NEW': 225})
        self.assertEqual(len(vi), 500);self.assertEqual(len(en), 500)

    def test_protected_rows_are_exactly_the_275_live_english_posts(self):
        snapshot = {p['id']: p for p in load(matrix.DATA / 'live-posts-2026-10-22.json')['posts']}
        kept = {r['wp_id']: r for r in self.m['en']['rows'] if r['kind'] == 'EXISTING_PROTECTED'}
        self.assertEqual(set(kept), set(snapshot))
        for wp_id, row in kept.items():
            self.assertEqual(row['proposed_url'], snapshot[wp_id]['link']);self.assertEqual(row['slug'], snapshot[wp_id]['slug'])
            self.assertEqual(row['category_ids'], snapshot[wp_id]['categories'])

    def test_every_new_row_has_a_real_leaf_category_of_its_language_and_a_clean_url(self):
        for lang, m in self.m.items():
            for r in (x for x in m['rows'] if x['kind'] == 'NEW'):
                cat = self.tax[r['category_id']]
                self.assertEqual((cat['language'], cat['role']), (lang, 'leaf'), r['id'])
                self.assertEqual(r['category_path'], cat['path_ids']);self.assertEqual(r['category_url'], cat['url'])
                self.assertEqual(split_url(r['proposed_url']), (lang, r['slug']));self.assertEqual(r['proposed_url'], post_url(lang, r['slug']))
                self.assertTrue(r['hub_url'].startswith(SITE) and self.tax[r['hub_category_id']]['language'] == lang)

    def test_vietnamese_rows_never_use_english_categories_or_urls_and_vice_versa(self):
        for r in self.m['vi']['rows']:
            self.assertTrue(r['proposed_url'].startswith(SITE + '/vi/'), r['id']);self.assertIn(140, r['category_path'])
        for r in (x for x in self.m['en']['rows'] if x['kind'] == 'NEW'):
            self.assertFalse(r['proposed_url'].startswith(SITE + '/vi/'), r['id']);self.assertNotIn(140, r['category_path'])

    def test_slugs_and_urls_are_unique_across_both_languages_posts_and_pages(self):
        everything = [r for m in self.m.values() for r in m['rows']]
        slugs = [r['slug'] for r in everything]
        self.assertEqual(len(slugs), len(set(slugs)))
        urls = [r['proposed_url'] for r in everything]
        self.assertEqual(len(urls), len(set(urls)))
        pages = matrix.existing()
        self.assertFalse(set(slugs) & ({p['slug'] for p in pages['pages']} | pages['reserved'] | {q['slug'] for q in pages['queued']}))

    def test_allocation_stays_close_to_the_editorial_suggestion(self):
        for lang, m in self.m.items():
            planned = {int(k): v for k, v in self.plan['suggested_' + lang + '_new_topics_by_category'].items()}
            actual = Counter(r['category_id'] for r in m['rows'] if r['kind'] == 'NEW')
            self.assertEqual(set(actual), set(planned))
            for cid, want in planned.items():
                self.assertLessEqual(abs(actual[cid] - want), max(3, round(want * 0.2)), (lang, cid))

    def test_no_row_claims_progress_research_or_a_live_dedup_it_did_not_do(self):
        for m in self.m.values():
            for r in (x for x in m['rows'] if x['kind'] == 'NEW'):
                self.assertEqual((r['writer_state'], r['checkpoint'], r['dedup']['live_recheck'], r['demand_evidence']),
                                 ('NEEDS_SOURCE', None, 'PENDING', 'NOT_MEASURED'), r['id'])
                self.assertTrue(r['source_requirements']);self.assertGreaterEqual(len(r['internal_link_plan']['links']), 3)

    def test_vietnamese_service_urls_are_never_invented(self):
        for r in self.m['vi']['rows']:
            self.assertIsNone(r['service_target']['url']);self.assertEqual(r['service_target']['url_status'], 'PENDING_LIVE_VI_PAGE_INVENTORY')

    def test_legal_and_regulated_topics_demand_an_official_source(self):
        pattern = ('giấy phép', 'bằng lái', 'gplx', 'mức phạt', 'luật', 'licence', 'license', 'idp', 'legal', 'fine')
        for m in self.m.values():
            for r in (x for x in m['rows'] if x['kind'] == 'NEW'):
                if any(w in (r['title'] + ' ' + r['primary_keyword']).lower() for w in pattern):
                    self.assertIn('official_vn_law', r['source_requirements'], r['id'] + ' ' + r['title'])

    def test_priority_one_rows_are_written_first_and_write_order_is_a_permutation(self):
        for lang, m in self.m.items():
            new = [r for r in m['rows'] if r['kind'] == 'NEW']
            self.assertEqual(sorted(r['write_order'] for r in new), list(range(1, len(new) + 1)))
            ordered = sorted(new, key=lambda r: r['write_order'])
            self.assertEqual([r['priority'] for r in ordered], sorted(r['priority'] for r in ordered))

    def test_a_matrix_row_is_not_an_admissible_topic_until_sources_and_review_exist(self):
        import tempfile
        from thuha.audit import snapshot_inventory
        row = self.m['vi']['rows'][0]
        shell = matrix.candidate_shell(row)
        with tempfile.TemporaryDirectory() as temp:
            inv = snapshot_inventory();inv['captured_at'] = __import__('thuha.common', fromlist=['now']).now()
            with self.assertRaises(ValueError):validate_candidate(shell, inv, [], LocalStore(temp))


class ValidatorRuleTests(unittest.TestCase):
    def test_a_clean_seed_passes(self):
        self.assertEqual(codes('vi', [seed()]), set())

    def test_place_or_model_swaps_of_one_template_are_blocked(self):
        a = seed(t='Thuê xe máy ở Cầu Giấy cần chuẩn bị giấy tờ gì', k='giấy tờ thuê xe cầu giấy', u='giay-to-thue-xe-cau-giay-can-gi')
        b = seed(t='Thuê xe máy ở Đống Đa cần chuẩn bị giấy tờ gì', k='giấy tờ thuê xe đống đa', u='giay-to-thue-xe-dong-da-can-gi',
                 q='Một người ở khu vực khác muốn biết cần mang giấy tờ gì trước khi nhận xe từ cửa hàng.')
        self.assertTrue(codes('vi', [a, b]) & {'TEMPLATE_VARIANT_OF_ANOTHER_ROW', 'TITLES_TOO_SIMILAR'})
        c = seed(t='So sánh Honda Vision và Air Blade cho người đi làm', k='vision air blade đi làm', u='so-sanh-vision-air-blade-di-lam', c=156)
        d = seed(t='So sánh Honda Lead và Janus cho người đi làm', k='lead janus đi làm', u='so-sanh-lead-janus-di-lam', c=156,
                 q='Một người đi làm hằng ngày muốn chọn giữa hai mẫu xe ga khác để di chuyển quãng ngắn.')
        self.assertTrue(codes('vi', [c, d]) & {'TEMPLATE_VARIANT_OF_ANOTHER_ROW', 'TITLES_TOO_SIMILAR'})

    def test_prices_and_unverifiable_claims_are_blocked_in_titles_and_keywords(self):
        for title in ('Thuê xe máy 150k một ngày ở Hà Nội cần biết gì', 'Thuê xe máy rẻ nhất Hà Nội cho khách mới', 'Thuê xe máy miễn cọc có thật không nhỉ'):
            self.assertIn('UNVERIFIABLE_PRICE_OR_CLAIM_IN_TITLE_OR_KEYWORD', codes('vi', [seed(t=title)]), title)

    def test_duplicates_slug_collisions_and_reserved_words_are_blocked(self):
        self.assertIn('DUPLICATE_KEYWORD', codes('vi', [seed(), seed(t='Một tiêu đề khác hẳn về cách trả xe đúng giờ', u='tra-xe-dung-gio-khong-bi-phat')]))
        self.assertIn('SLUG_COLLIDES_WITH_EXISTING_OR_RESERVED', codes('vi', [seed(u='faq-faq-faq')]) | codes('vi', [seed(u='contact-us')]))
        self.assertIn('SLUG_COLLIDES_WITH_EXISTING_OR_RESERVED', codes('vi', [seed(u='cheap-motorbike-rental-in-hanoi')]))  # a live EN slug

    def test_wrong_language_text_and_wrong_category_language_are_blocked(self):
        self.assertTrue({c for c in codes('vi', [seed(t='A quiet route plan with practical guidance for riders in town')]) if c.startswith('WRONG_LANGUAGE')})
        self.assertIn('CATEGORY_NOT_A_LEAF_OF_LANGUAGE', codes('vi', [seed(c=123)]))   # an English category
        self.assertIn('CATEGORY_NOT_A_LEAF_OF_LANGUAGE', codes('vi', [seed(c=146)]))   # a hub, not a leaf

    def test_english_rows_too_close_to_an_existing_post_are_blocked(self):
        s = {'c': 123, 't': 'Hanoi Motorbike Rental Deposits: How to Record Payment and Return', 'k': 'record deposit payment return',
             'q': 'A renter wants to record how a rental deposit was paid and returned to avoid a later dispute.', 'i': 'transactional_support',
             's': 'faq', 'r': ['first_party_facts'], 'p': 1, 'u': 'record-deposit-payment-and-return-in-hanoi'}
        self.assertIn('TOO_CLOSE_TO_EXISTING_POST', codes('en', [s]))

    def test_validation_catches_a_wrong_total_a_bad_id_and_fabricated_progress(self):
        m = load(matrix.matrix_path('vi'))
        short = copy.deepcopy(m);short['rows'].pop()
        self.assertIn('ROW_COUNT', {p['code'] for p in matrix.validate(short, 'vi')})
        claimed = copy.deepcopy(m);claimed['rows'][0]['writer_state'] = 'READY'
        self.assertIn('STATE_CLAIMS_PROGRESS_WITHOUT_EVIDENCE', {p['code'] for p in matrix.validate(claimed, 'vi')})
        wrong_url = copy.deepcopy(m);wrong_url['rows'][1]['proposed_url'] = SITE + '/' + wrong_url['rows'][1]['slug'] + '/'
        self.assertIn('URL_NAMESPACE', {p['code'] for p in matrix.validate(wrong_url, 'vi')})
        en = load(matrix.matrix_path('en'))
        lost = copy.deepcopy(en);lost['rows'] = [r for r in lost['rows'] if r.get('wp_id') != 150]
        self.assertTrue({p['code'] for p in matrix.validate(lost, 'en')} & {'ROW_COUNT', 'EXISTING_POSTS_NOT_EXACTLY_PROTECTED'})


if __name__ == '__main__':
    unittest.main()
