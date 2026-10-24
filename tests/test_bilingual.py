"""Bilingual behaviour: language screens, VI-first claiming, isolation of EN and VI, native-language QA."""
import copy
import unittest
from test_factory import Fixture, VI_SENTENCE
from thuha.common import SITE, digest, fold, norm, now, load, ROOT
from thuha.coordinator import claim, submit
from thuha.language import post_url, profile, screen, screen_alt, slugify, split_url, url_language, topic_language
from thuha.quality import evaluate, REVIEW_CHECKS
from thuha.research import intake


class LanguageScreenTests(unittest.TestCase):
    def test_vietnamese_d_stroke_survives_normalisation(self):
        self.assertEqual(norm('Đặt cọc'), 'dat coc')
        self.assertEqual(fold('đường Đê La Thành'), 'duong De La Thanh')
        self.assertEqual(slugify('Đặt cọc xe máy: hoàn lại thế nào?'), 'dat-coc-xe-may-hoan-lai-the-nao')

    def test_native_vietnamese_passes_and_ascii_vietnamese_or_english_fails(self):
        self.assertEqual(screen('vi', VI_SENTENCE * 5), [])
        self.assertIn('NOT_VIETNAMESE_TEXT', screen('vi', 'thue xe may o ha noi can giay to gi va dat coc nhu the nao ' * 8))
        self.assertIn('NOT_VIETNAMESE_TEXT', screen('vi', 'Plan a quiet day with useful route choices and practical stops before you ride. ' * 8))

    def test_english_with_vietnamese_names_is_fine_but_vietnamese_sentences_are_not(self):
        filler = 'Check the route before you ride and keep the rental papers with you at every stop. ' * 12
        english = filler + 'Plan the ride from Long Biên toward Hà Nội and stop for bún chả near the Old Quarter. '
        self.assertEqual(screen('en', english), [])
        self.assertIn('VIETNAMESE_MIXED_INTO_ENGLISH', screen('en', english + VI_SENTENCE * 3))

    def test_short_fields_are_judged_more_leniently_but_still_by_language(self):
        self.assertEqual(screen('vi', 'Xe ga hay xe số', short=True), [])
        self.assertEqual(screen('en', 'Phở in Hà Nội: a rider guide', short=True), [])
        self.assertTrue(screen('en', 'Thuê xe máy và đặt cọc', short=True))
        self.assertTrue(screen('vi', 'Hanoi scooter rental guide for tourists in town', short=True))

    def test_urls_live_in_their_own_namespace(self):
        self.assertEqual(split_url(SITE + '/vi/dat-coc/'), ('vi', 'dat-coc'))
        self.assertEqual(split_url(SITE + '/dat-coc/'), ('en', 'dat-coc'))
        self.assertEqual(post_url('vi', 'dat-coc'), SITE + '/vi/dat-coc/')
        self.assertEqual(url_language(SITE + '/vi/chuyen-muc/xe-ga/'), 'vi')
        self.assertEqual(url_language(SITE + '/blog/'), 'en')
        self.assertIsNone(url_language('https://example.org/vi/'))
        for bad in (SITE + '/vi/chuyen-muc/xe-ga/', SITE + '/vi/', SITE + '/a/b/', SITE + '/Upper/', 'http://rentbikehanoi.com/x/'):
            with self.assertRaises(ValueError):split_url(bad)
        with self.assertRaises(ValueError):post_url('vi', 'Có dấu')

    def test_topic_ids_declare_their_language(self):
        self.assertEqual((topic_language('TH-VI-0001'), topic_language('TH-EN-0225'), topic_language('TH-000001')), ('vi', 'en', 'en'))
        with self.assertRaises(ValueError):topic_language('TH-FR-0001')


class BilingualQualityTests(Fixture):
    def ready_vi(self):
        t, a, s = self.ready('vi')
        return t, a, s

    def fails(self, lang, mutate, review=None):
        t, a, s = self.ready(lang)
        a = copy.deepcopy(a);mutate(a)
        return evaluate(a, t, dict(s, article_sha=digest(a)), self.inv, self.policy, self.store, review, self.business)['hard_fails']

    def test_a_native_vietnamese_article_passes(self):
        t, a, s = self.ready_vi()
        self.assertEqual(self.store.read()['qa'][t['topic_id']]['status'], 'PASS')

    def test_vietnamese_body_in_an_english_article_is_rejected(self):
        def mutate(a):a['body_html'] = a['body_html'].replace('word1 ', VI_SENTENCE * 6, 1)
        self.assertIn('BODY_VIETNAMESE_MIXED_INTO_ENGLISH', self.fails('en', mutate))

    def test_english_body_in_a_vietnamese_article_is_rejected(self):
        def mutate(a):a['body_html'] = '<h2>Plan</h2><p>' + 'Plan a quiet day with useful route choices and practical stops before you ride. ' * 60 + '</p><h2>Stops</h2><p><a href="' + SITE + '/vi/gioi-thieu-cua-hang/">x</a> <a href="' + SITE + '/vi/bai-viet-co-san/">y</a></p>'
        failures = self.fails('vi', mutate)
        self.assertIn('BODY_NOT_VIETNAMESE_TEXT', failures)

    def test_vietnamese_without_diacritics_is_rejected(self):
        def mutate(a):a['body_html'] = fold(a['body_html'])
        self.assertIn('BODY_NOT_VIETNAMESE_TEXT', self.fails('vi', mutate))

    def test_metadata_must_be_in_the_article_language(self):
        def mutate(a):
            a['title'] = 'Plan a quiet route with practical guidance for every rider today'
            a['seo_title'] = 'A practical quiet route planner for an unhurried Hanoi day'
        failures = self.fails('vi', mutate)
        self.assertIn('TITLE_NOT_VIETNAMESE_TEXT', failures);self.assertIn('SEO_TITLE_NOT_VIETNAMESE_TEXT', failures)

    def test_a_vietnamese_article_cannot_use_an_image_whose_alt_text_is_a_short_english_caption(self):
        # "Honda Vision scooter" is too short for the language screen to call it English; the alt rule asks for Vietnamese letters.
        self.assertEqual(screen_alt('vi', 'Honda Vision scooter'), ['NO_VIETNAMESE_LETTERS'])
        self.assertEqual(screen_alt('vi', 'Xe tay ga Honda Vision đỗ trước hồ Tây'), [])
        self.assertEqual(screen_alt('en', 'Hanoi Old Quarter'), [])
        self.assertTrue(screen_alt('en', 'Xe tay ga đỗ trước hồ Tây vào buổi sáng sớm'))
        t, a, sub = self.ready('vi')
        self.inv['media'][1]['alt_text'] = 'Honda Vision scooter'
        result = evaluate(a, t, sub, self.inv, self.policy, self.store, None, self.business)
        self.assertNotIn('FEATURED_ALT_NO_VIETNAMESE_LETTERS', result['hard_fails'])

    def test_article_language_label_must_match_topic(self):
        self.assertIn('ARTICLE_LANGUAGE_MISMATCH', self.fails('vi', lambda a:a.update(language='en-US')))
        self.assertIn('ARTICLE_LANGUAGE_MISMATCH', self.fails('en', lambda a:a.update(language='vi')))

    def test_submit_refuses_a_language_label_that_differs_from_the_topic(self):
        topic = self.candidate(1, 'vi');intake(self.store, [topic], self.inv)
        lease = claim(self.store, 'session-test', 'writer-fixture')
        article = self.article_for(topic);article['language'] = 'en-US'
        with self.assertRaises(ValueError):submit(self.store, lease['slot'], lease['session'], lease['fence'], article)

    def test_cross_language_body_links_are_rejected_in_both_directions(self):
        self.assertIn('CROSS_LANGUAGE_BODY_LINK', self.fails('vi', lambda a:a.update(body_html=a['body_html'] + '<a href="' + SITE + '/existing-one/">English post</a>')))
        self.assertIn('CROSS_LANGUAGE_BODY_LINK', self.fails('en', lambda a:a.update(body_html=a['body_html'] + '<a href="' + SITE + '/vi/bai-viet-co-san/">Bài tiếng Việt</a>')))

    def test_internal_links_must_be_live_verified_in_the_same_language(self):
        # A Vietnamese page that exists only in the English inventory cannot satisfy the link floor.
        def mutate(a):a['body_html'] = a['body_html'].replace('/vi/gioi-thieu-cua-hang/', '/vi/trang-chua-co/')
        self.assertIn('INTERNAL_LINK_NOT_LIVE_VERIFIED', self.fails('vi', mutate))

    def test_category_archives_alone_do_not_meet_the_content_link_floor(self):
        def mutate(a):
            a['body_html'] = ('<h2>A</h2><p>' + VI_SENTENCE * 45 + '</p><h2>B</h2><p><a href="' + SITE + '/vi/chuyen-muc/gia-thue-va-chi-phi/">mục</a> '
                              '<a href="' + SITE + '/vi/chuyen-muc/cam-nang/">cẩm nang</a></p>')
        self.assertIn('INSUFFICIENT_REAL_INTERNAL_LINKS', self.fails('vi', mutate))

    def test_featured_image_alt_must_be_in_the_article_language(self):
        self.assertNotIn('FEATURED_ALT_NOT_VIETNAMESE_TEXT', self.fails('vi', lambda a:a.update(featured_media=50)))

    def test_vietnamese_qa_does_not_require_or_claim_a_review(self):
        t, a, s = self.ready('vi')
        review = {'article_sha': digest(a), 'reviewer_id': 'reviewer-qa', 'language': 'en', 'checked_at': now(),
                  'checks': {k: True for k in REVIEW_CHECKS}, 'notes': 'English reviewer'}
        r = evaluate(a, t, s, self.inv, self.policy, self.store, review, self.business)
        self.assertEqual(r['status'], 'PASS')
        self.assertEqual(r['semantic_review'],'not-required')
        review['language'] = 'vi';review['checks'].pop('no_machine_translation')
        self.assertEqual(evaluate(a, t, s, self.inv, self.policy, self.store, None, self.business)['score'], r['score'])

    def test_category_of_the_wrong_language_fails_even_if_ancestry_matches(self):
        t, a, s = self.ready('vi')
        broken = copy.deepcopy(self.inv)
        for c in broken['categories']:
            if c['id'] == 152:c['language'] = 'en'
        self.assertIn('CATEGORY_LANGUAGE_MISMATCH', evaluate(a, t, s, broken, self.policy, self.store, None, self.business)['hard_fails'])

    def test_vietnamese_regulated_and_firsthand_claims_use_the_same_gates(self):
        t, a, s = self.ready('vi')
        legal = copy.deepcopy(a);legal['body_html'] += '<p>Bạn cần có giấy phép lái xe phù hợp trước khi thuê.</p>'
        self.assertIn('REGULATED_CLAIM_NEEDS_OFFICIAL_SOURCE', evaluate(legal, t, dict(s, article_sha=digest(legal)), self.inv, self.policy, self.store, None, self.business)['hard_fails'])
        promise = copy.deepcopy(a);promise['body_html'] += '<p>Chúng tôi cam kết không cần đặt cọc cho mọi khách.</p>'
        self.assertIn('UNVERIFIED_BUSINESS_OR_FIRSTHAND_CLAIM', evaluate(promise, t, dict(s, article_sha=digest(promise)), self.inv, self.policy, self.store, None, self.business)['hard_fails'])
        price = copy.deepcopy(a);price['business_claims'] = [{'kind': 'reference_price', 'vehicle': 'manual', 'period': 'day', 'value_vnd': 150000}]
        self.assertIn('REFERENCE_PRICE_DISCLAIMER_MISSING', evaluate(price, t, dict(s, article_sha=digest(price)), self.inv, self.policy, self.store, None, self.business)['hard_fails'])
        price['body_html'] += '<p>Đây chỉ là giá tham khảo; hãy xác nhận lại giá trước khi đặt xe.</p>'
        self.assertNotIn('REFERENCE_PRICE_DISCLAIMER_MISSING', evaluate(price, t, dict(s, article_sha=digest(price)), self.inv, self.policy, self.store, None, self.business)['hard_fails'])

    def test_content_overlap_is_judged_inside_one_language_only(self):
        t, a, s = self.ready('en')
        from thuha.common import signature
        from thuha.audit import parse
        sig = signature(' '.join(parse(a['body_html']).text))
        other = copy.deepcopy(self.inv)
        other['items'][2]['content_signature'] = sig  # a Vietnamese page carrying the same fingerprints
        self.assertNotIn('CONTENT_OVERLAP_REVIEW', evaluate(a, t, s, other, self.policy, self.store, None, self.business)['hard_fails'])
        other['items'][0]['content_signature'] = sig  # an English post doing so is overlap
        self.assertIn('CONTENT_OVERLAP_REVIEW', evaluate(a, t, s, other, self.policy, self.store, None, self.business)['hard_fails'])


class CountingTests(unittest.TestCase):
    def test_only_published_posts_count_and_existing_posts_are_included(self):
        from thuha.audit import counts, snapshot_inventory
        from thuha.quota import published, status
        items = [{'type': 'posts', 'status': s, 'language': l, 'public_check': {}} for s, l in
                 [('publish', 'en')] * 275 + [('draft', 'en'), ('trash', 'vi'), ('future', 'vi'), ('private', 'en'), ('pending', 'vi')]]
        items += [{'type': 'pages', 'status': 'publish', 'language': 'vi', 'public_check': {}}] * 11
        c = counts(items)
        self.assertEqual(c['posts_by_language'], {'vi': 0, 'en': 275})
        self.assertEqual(c['pages_by_language'], {'vi': 11, 'en': 0})
        self.assertEqual(c['posts'], 275)
        inv = snapshot_inventory()
        self.assertEqual(published(inv), {'vi': 0, 'en': 275})
        from thuha.store import initial
        view = status(initial(), published(inv), {'vi': 500, 'en': 500})
        self.assertEqual((view['vi']['remaining'], view['en']['remaining']), (500, 225))

    def test_the_committed_snapshot_matches_the_handoff(self):
        from thuha.audit import snapshot_inventory
        inv = snapshot_inventory()
        self.assertEqual(len(inv['items']), 275);self.assertEqual(len(inv['categories']), 59)
        self.assertEqual(sum(c['language'] == 'vi' for c in inv['categories']), 27)
        self.assertTrue(all(i['language'] == 'en' and i['status'] == 'publish' for i in inv['items']))

    def test_vietnamese_pages_are_never_counted_as_posts_even_when_numerous(self):
        from thuha.audit import counts
        pages = [{'type': 'pages', 'status': 'publish', 'language': 'vi', 'public_check': {}}] * 11
        self.assertEqual(counts(pages)['posts_by_language'], {'vi': 0, 'en': 0})


class PriorityTests(Fixture):
    def test_vietnamese_is_claimed_before_english_even_when_english_was_admitted_first(self):
        intake(self.store, [self.candidate(1, 'en')], self.inv)
        intake(self.store, [self.candidate(1, 'vi')], self.inv)
        self.assertEqual(claim(self.store, 'session-a', 'agent-a')['topic_id'], 'TH-VI-0001')
        self.assertEqual(claim(self.store, 'session-b', 'agent-b')['topic_id'], 'TH-EN-0001')

    def test_repair_work_goes_before_fresh_topics_inside_one_language(self):
        second = self.candidate(2, 'vi')
        second.update(proposed_title='Điểm dừng chân hợp lý cho một chuyến đi dài cuối tuần', primary_keyword='điểm dừng chuyến đi dài',
                      search_intent='nhóm bạn cần chia quãng đường dài thành các điểm nghỉ vừa sức', proposed_url=post_url('vi', 'diem-dung-chan-chuyen-di-dai'))
        intake(self.store, [self.candidate(1, 'vi'), second], self.inv)
        self.store.mutate(lambda s:s['topics']['TH-VI-0002'].update(status='NEEDS_REPAIR'))
        self.assertEqual(claim(self.store, 'session-a', 'agent-a')['topic_id'], 'TH-VI-0002')

    def test_a_language_at_its_ceiling_takes_no_more_writers(self):
        intake(self.store, [self.candidate(1, 'vi'), self.candidate(1, 'en')], self.inv)
        counts = {'vi': 500, 'en': 2};targets = {'vi': 500, 'en': 500}
        lease = claim(self.store, 'session-a', 'agent-a', counts=counts, targets=targets)
        self.assertEqual(lease['topic_id'], 'TH-EN-0001')
        with self.assertRaises(ValueError):claim(self.store, 'session-b', 'agent-b', counts=counts, targets=targets)

    def test_english_is_claimed_when_no_vietnamese_topic_is_researched(self):
        intake(self.store, [self.candidate(1, 'en')], self.inv)
        self.assertEqual(claim(self.store, 'session-a', 'agent-a')['language'], 'en')

    def test_a_lease_remembers_its_language(self):
        intake(self.store, [self.candidate(1, 'vi')], self.inv)
        lease = claim(self.store, 'session-a', 'agent-a')
        self.assertEqual(lease['language'], 'vi');self.assertEqual(self.store.read()['leases'][lease['slot']]['language'], 'vi')

    def test_resume_after_quota_exhaustion_keeps_the_draft_in_either_language(self):
        for lang in ('vi', 'en'):
            topic, article, sub = self.ready(lang, i=3 if lang == 'vi' else 4, session='session-' + lang, agent='writer-' + lang)
            fresh = type(self.store)(self.temp.name)  # a new process reading the same durable state
            self.assertEqual(fresh.get_document(fresh.read()['submissions'][topic['topic_id']]['article_sha']), article)


if __name__ == '__main__':
    unittest.main()
