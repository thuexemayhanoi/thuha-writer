"""Writing support: the pack, the builder, the lint, the fix hints and the declaration of a wait.

All of it is read-only and none of it changes what QA decides; a lint never adds or removes a point.
"""
import re
import unittest
from thuha import quality, writing
from thuha.common import ROOT, load

CFG = writing.settings()
FACTS = load(ROOT / 'config/business-facts.json')


class BlocksTests(unittest.TestCase):
    def test_paragraphs_headings_and_anchors_are_read_in_order(self):
        html = '<h2>Một</h2><p>Đoạn <a href="https://x.test/a">liên kết thật</a> đầu.</p><ul><li>Mục<br>hai</li></ul><h3>Con</h3><p>Cuối.</p>'
        parsed = writing.blocks(html)
        self.assertEqual(parsed.headings, [(2, 'Một'), (3, 'Con')])
        self.assertEqual([t for _, t in parsed.blocks], ['Đoạn liên kết thật đầu.', 'Mục hai', 'Cuối.'])
        self.assertEqual(parsed.anchors, [('https://x.test/a', 'liên kết thật')])

    def test_money_is_read_only_with_a_currency_unit(self):
        text = 'Giá 150.000 đồng một ngày, tuần 700.000đ, tháng 1,2 triệu, hoặc 200k; gọi 0334 699 969, năm 2025, xe số 110 phân khối, VND 1,150,000.'
        self.assertEqual(sorted(writing.money(text, CFG)), sorted([150000, 700000, 1200000, 200000, 1150000]))
        self.assertEqual(writing.money('Mất 3 đêm và 5 đ nhỏ', CFG), [])  # a bare small number is not money

    def test_the_unit_after_a_range_serves_both_ends_and_a_variable_is_not_money(self):
        self.assertEqual(sorted(writing.money('Khoảng 1.000.000-1.200.000 đồng một tháng', CFG)), [1000000, 1200000])
        self.assertEqual(sorted(writing.money('a fine of 2,000,000 to 3,000,000 VND', CFG)), [2000000, 3000000])
        self.assertEqual(writing.money('Gọi cọc mỗi xe là K: nếu gộp thành một khoản 2K', CFG), [])  # algebra
        self.assertEqual(writing.money('khoảng 50k và 1,5k', CFG), [50000, 1500])

    def test_reference_matches_say_where_an_amount_comes_from(self):
        self.assertIn(('manual', 'day', 'endpoint'), writing.reference_matches(150000, FACTS))
        self.assertIn(('manual', 'day', 'inside'), writing.reference_matches(175000, FACTS))
        self.assertEqual(writing.reference_matches(333333, FACTS), [])


class SnippetTests(unittest.TestCase):
    def test_the_contact_line_is_written_from_the_confirmed_facts_only(self):
        vi, en = writing.contact_html('vi', FACTS, CFG), writing.contact_html('en', FACTS, CFG)
        for text in (vi, en):
            self.assertIn('Thuê xe máy Nguyễn Hà', text)
            self.assertIn('Ngõ 5 Nguyễn Văn Cừ', text)
            self.assertIn('<a href="tel:+84334699969">0334 699 969</a>', text)
            self.assertIn('09:00', text)
            self.assertIn('21:00', text)
        self.assertIn('09:00 đến 21:00', vi)
        self.assertIn('near Gia Lâm bus station', en)

    def test_the_contact_line_is_valid_html_for_the_policy_and_the_disclaimer_satisfies_qa(self):
        from thuha import htmlpolicy
        self.assertEqual(htmlpolicy.violations('<p>' + writing.contact_html('vi', FACTS, CFG) + '</p>'), [])
        for lang in ('vi', 'en'):
            self.assertTrue(re.search(quality.DISCLAIMER[lang], CFG['disclaimer'][lang], re.I), lang)

    def test_the_price_table_lists_every_interval_and_never_an_electric_day_rate(self):
        rows = {(r['vehicle'], r['period']): r for r in writing.price_table(FACTS, 'vi')}
        self.assertEqual(rows[('manual', 'day')]['text'], 'từ 150.000 đến 200.000 đồng')
        self.assertEqual(rows[('Vision', 'week')]['text'], '1.000.000 đồng')
        self.assertIsNone(rows[('electric', 'day')]['interval'])
        self.assertNotIn('claim_example', rows[('electric', 'day')])

    def test_every_claim_example_is_accepted_by_qa_as_an_approved_price(self):
        for row in writing.price_table(FACTS, 'vi'):
            if row.get('claim_example'):
                low, high = row['interval']
                self.assertTrue(low <= row['claim_example']['value_vnd'] <= high)


class HintTests(unittest.TestCase):
    def test_every_failure_code_qa_and_precheck_can_raise_has_a_hint(self):
        text = '\n'.join((ROOT / 'src/thuha' / name).read_text(encoding='utf-8') for name in ('quality.py', 'runtime.py', 'datawait.py'))
        codes = set(re.findall(r"errors\.append\('([A-Z][A-Z0-9_]+)'\)", text)) | set(re.findall(r"failures\.append\('([A-Z][A-Z0-9_]+)'\)", text))
        codes |= {'SCORE_BELOW_THRESHOLD_EVEN_WITH_THE_DATA', 'Inventory is stale or future-dated', 'Complete inventory for the exact production site is required'}
        codes |= {'PROVENANCE_TOPIC_ID', 'BODY_NOT_VIETNAMESE_TEXT', 'TITLE_ENGLISH_MIXED_INTO_VIETNAMESE', 'SEO_TITLE_EMPTY_TEXT', 'META_DESCRIPTION_EMPTY_TEXT',
                  'FOCUS_KEYWORD_EMPTY_TEXT', 'FEATURED_ALT_NO_VIETNAMESE_LETTERS', 'BODY_IMAGE_ALT_NOT_VIETNAMESE_TEXT', 'TITLE_NOT_CANONICAL_PLAIN_TEXT',
                  'META_DESCRIPTION_NOT_CANONICAL_PLAIN_TEXT'}
        self.assertGreater(len(codes), 25)
        for code in sorted(codes):
            hint = writing._hint_for(code, CFG['hints'])
            self.assertIsNotNone(hint, code + ' has no hint')
            self.assertTrue(hint['where'] and hint['fix'], code)

    def test_the_most_specific_pattern_wins(self):
        self.assertIn('Alt', writing._hint_for('BODY_IMAGE_ALT_NOT_VIETNAMESE_TEXT', CFG['hints'])['fix'])
        self.assertIn('Văn bản thuần', writing._hint_for('TITLE_NOT_CANONICAL_PLAIN_TEXT', CFG['hints'])['fix'])
        self.assertIn('đúng ngôn ngữ', writing._hint_for('TITLE_ENGLISH_MIXED_INTO_VIETNAMESE', CFG['hints'])['fix'])
        self.assertIn('Điền từ khóa', writing._hint_for('FOCUS_KEYWORD_MISSING', CFG['hints'])['fix'])

    def test_an_unknown_code_is_said_to_be_unknown_not_hidden(self):
        out = writing.hints(['SOMETHING_NEW'], CFG)
        self.assertEqual((out[0]['code'], out[0]['where']), ('SOMETHING_NEW', 'unknown'))


class LintTests(unittest.TestCase):
    TOPIC = {'language': 'vi', 'primary_keyword': 'thuê xe máy theo tuần'}

    def article(self, body, **fields):
        base = {'body_html': body, 'seo_title': 'Thuê xe máy theo tuần ở Hà Nội: cách tính', 'title': 'Thuê xe máy theo tuần ở Hà Nội',
                'meta_description': 'Cách tính tiền khi thuê xe máy theo tuần, so với thuê theo ngày và theo tháng, kèm điều cần xác nhận.',
                'focus_keyword': 'thuê xe máy theo tuần', 'business_claims': []}
        base.update(fields)
        return base

    def codes(self, article, others=None, severity=None):
        return [f['code'] for f in writing.lint(article, self.TOPIC, FACTS, others, CFG) if severity is None or f['severity'] == severity]

    GOOD = ('<h2>Mở đầu</h2><p>Khi thuê xe máy theo tuần, người thuê cần tính tổng số ngày trước khi chọn gói.</p><h2>Cách tính</h2><p>Đếm số ngày thật sự dùng xe và so với giá.</p>'
            '<h2>Điều cần hỏi</h2><p>Hỏi cửa hàng về giờ nhận và giờ trả xe.</p>')

    def test_a_clean_article_has_no_fix_level_finding(self):
        self.assertEqual(self.codes(self.article(self.GOOD), severity='fix'), [])

    def test_markdown_is_caught_because_wordpress_would_print_it_as_it_is(self):
        self.assertIn('LINT_MARKDOWN_RESIDUE', self.codes(self.article(self.GOOD + '<p>**đậm** và [liên kết](https://x.test)</p>')))

    def test_broken_heading_levels_are_caught(self):
        for body in ('<h3>Sai cấp</h3><p>a b c</p>', '<h2>Một</h2><h4>Nhảy cấp</h4><p>a</p>', '<h1>Không được</h1><p>a</p>', '<h2></h2><p>a</p>'):
            self.assertIn('LINT_HEADING_LEVEL', self.codes(self.article(body)), body)
        self.assertNotIn('LINT_HEADING_LEVEL', self.codes(self.article('<h2>Một</h2><h3>Con</h3><h3>Con hai</h3><h2>Hai</h2><p>a</p>')))

    def test_a_reference_price_must_be_declared_and_come_with_the_disclaimer(self):
        body = self.GOOD + '<p>Giá một tuần khoảng 700.000 đồng.</p>'
        found = writing.lint(self.article(body), self.TOPIC, FACTS, None, CFG)
        codes = {f['code'] for f in found}
        self.assertTrue({'LINT_PRICE_NOT_DECLARED', 'LINT_DISCLAIMER_MISSING'} <= codes)
        undeclared = next(f for f in found if f['code'] == 'LINT_PRICE_NOT_DECLARED')
        self.assertEqual(undeclared['severity'], 'fix')  # no claim at all: QA would not see this price
        self.assertIn({'vehicle': 'manual', 'period': 'week'}, undeclared['candidates'])
        fixed = self.article(body + '<p>' + CFG['disclaimer']['vi'] + '</p>', business_claims=[{'kind': 'reference_price', 'vehicle': 'manual', 'period': 'week', 'value_vnd': 700000}])
        self.assertEqual([c for c in self.codes(fixed) if c in ('LINT_PRICE_NOT_DECLARED', 'LINT_DISCLAIMER_MISSING')], [])

    PRICE_CODES = ('LINT_PRICE_NOT_APPROVED', 'LINT_PRICE_NOT_DECLARED', 'LINT_PRICE_INSIDE_INTERVAL', 'LINT_POLICY_AMOUNT', 'LINT_DISCLAIMER_MISSING')

    def price_codes(self, sentence, **fields):
        return [c for c in self.codes(self.article(self.GOOD + '<p>' + sentence + '</p>', **fields)) if c in self.PRICE_CODES]

    def test_an_amount_the_shop_never_gave_is_a_fix_when_a_sentence_presents_it_as_the_shops(self):
        self.assertIn('LINT_PRICE_NOT_APPROVED', self.price_codes('Thuê xe máy Nguyễn Hà tính 333.000 đồng một ngày.'))
        self.assertEqual(self.price_codes('Ví dụ, nếu cửa hàng tính 333.000 đồng một ngày thì ba ngày là 999.000 đồng.'), [])  # said to be hypothetical

    def test_a_fine_a_fee_or_the_arithmetic_of_an_example_is_not_a_shop_price_even_when_a_number_equals_one(self):
        self.assertEqual(self.price_codes('Mức phạt không đội mũ bảo hiểm là từ 400.000 đến 600.000 đồng.'), [])  # 600.000 is also a weekly reference price
        self.assertEqual(self.price_codes('Ví dụ: 4 x 150.000 = 600.000 đồng.'), [])
        self.assertEqual(self.price_codes('Tổng cộng 333.000 đồng.'), [])
        self.assertEqual(self.price_codes('A fine of 2,000,000 to 3,000,000 VND applies.'), [])

    def test_an_amount_tied_to_a_policy_the_shop_has_not_confirmed_is_a_fix(self):
        self.assertIn('LINT_POLICY_AMOUNT', self.price_codes('Thuê xe máy Nguyễn Hà thu cọc 500.000 đồng khi nhận xe.'))
        self.assertEqual(self.price_codes('Ví dụ, nếu cửa hàng thu cọc 500.000 đồng thì hãy hỏi khi nào được hoàn lại.'), [])

    def test_the_extension_fee_the_owner_confirmed_is_an_approved_amount_and_an_invented_one_is_not(self):
        without = {k: v for k, v in FACTS.items() if k != 'extension_policy'}
        facts = dict(without, extension_policy={'hourly_rate_vnd': 20000, 'one_rental_day_when_extension_hours_exceed': 6, 'confirmed_by': 'website owner'})
        sentence = '<p>Thuê xe máy Nguyễn Hà tính phí gia hạn %s đồng mỗi giờ.</p>'
        codes = lambda amount, business: [f['code'] for f in writing.lint(self.article(self.GOOD + sentence % amount), self.TOPIC, business, None, CFG)]
        self.assertNotIn('LINT_PRICE_NOT_APPROVED', codes('20.000', facts))
        self.assertIn('LINT_PRICE_NOT_APPROVED', codes('30.000', facts))  # the old rate was superseded and is not a fact
        self.assertIn('LINT_PRICE_NOT_APPROVED', codes('20.000', without))  # nothing confirmed it in a file that holds no such policy

    def test_a_point_inside_an_interval_is_a_precision_the_shop_did_not_state(self):
        article = self.article(self.GOOD + '<p>Giá thuê khoảng 175.000 đồng một ngày. ' + CFG['disclaimer']['vi'] + '</p>',
                               business_claims=[{'kind': 'reference_price', 'vehicle': 'manual', 'period': 'day', 'value_vnd': 175000}])
        self.assertIn('LINT_PRICE_INSIDE_INTERVAL', self.codes(article))

    def test_a_declared_claim_the_text_never_writes_is_noted(self):
        article = self.article(self.GOOD, business_claims=[{'kind': 'reference_price', 'vehicle': 'manual', 'period': 'day', 'value_vnd': 150000}])
        self.assertIn('LINT_CLAIM_NOT_IN_TEXT', self.codes(article))

    def test_provenance_must_not_leak_into_the_voice_of_the_shop(self):
        for phrase in ('Thông tin này do chủ cửa hàng cung cấp.', 'Là một mô hình ngôn ngữ, tôi không biết.'):
            self.assertIn('LINT_SOURCE_NOTE_LEAK', self.codes(self.article(self.GOOD + '<p>' + phrase + '</p>')), phrase)

    def test_padding_by_repeating_a_sentence_is_caught_but_one_honest_repetition_of_a_short_phrase_is_not(self):
        sentence = 'Hãy xác nhận lại giờ nhận xe và giờ trả xe với cửa hàng trước khi chuyển tiền.'
        self.assertIn('LINT_PADDING', self.codes(self.article(self.GOOD + '<p>' + sentence + '</p><p>' + sentence + '</p>')))
        self.assertNotIn('LINT_PADDING', self.codes(self.article(self.GOOD)))

    def test_generic_anchor_text_and_a_long_meta_are_noted_as_things_to_consider(self):
        article = self.article(self.GOOD + '<p>Xem <a href="https://rentbikehanoi.com/vi/x/">tại đây</a>.</p>', meta_description='m' * 170)
        codes = self.codes(article, severity='consider')
        self.assertIn('LINT_GENERIC_ANCHOR', codes)
        self.assertIn('LINT_META_TOO_LONG', codes)

    def test_the_shop_phone_link_is_not_a_generic_anchor(self):
        self.assertNotIn('LINT_GENERIC_ANCHOR', self.codes(self.article(self.GOOD + '<p><a href="tel:+84334699969">0334 699 969</a></p>')))

    def test_the_focus_keyword_should_appear_in_the_body_and_in_a_headline(self):
        article = self.article('<h2>Khác</h2><p>Nội dung hoàn toàn khác.</p>', seo_title='Một tiêu đề khác', title='Khác', meta_description='Mô tả khác hẳn, đủ dài để không bị cảnh báo độ dài của phần mô tả này.')
        codes = self.codes(article)
        self.assertIn('LINT_KEYWORD_NOT_IN_BODY', codes)
        self.assertIn('LINT_KEYWORD_NOT_IN_HEADLINES', codes)

    def test_two_articles_that_share_paragraphs_are_a_template_and_a_shared_contact_line_is_not(self):
        shared = ('Trước khi nhận xe, hãy chụp ảnh toàn bộ thân xe, đồng hồ và lốp, rồi gửi cho cửa hàng để hai bên cùng giữ một bản ghi tình trạng chiếc xe lúc bắt đầu thuê. '
                  'Cách làm này giúp tránh tranh luận về vết xước cũ khi trả xe và chỉ mất vài phút khi nhận xe.')
        mine = self.article('<h2>Đầu</h2><p>Một nội dung riêng về tính ngày.</p><h2>Giữa</h2><p>' + shared + '</p><h2>Cuối</h2><p>Kết thúc riêng.</p>')
        other = '<h2>Khác</h2><p>Nội dung khác hẳn.</p><h2>Cũng khác</h2><p>' + shared + '</p>'
        found = [f for f in writing.lint(mine, self.TOPIC, FACTS, {'TH-VI-0099': other}, CFG) if f['code'] == 'LINT_TEMPLATE_SIMILARITY']
        self.assertTrue(found)
        self.assertEqual(found[0]['other'], 'TH-VI-0099')
        contact = '<p>' + writing.contact_html('vi', FACTS, CFG) + '</p>'
        quiet = writing.lint(self.article(self.GOOD + contact), self.TOPIC, FACTS, {'TH-VI-0099': '<h2>Khác</h2><p>Chuyện khác.</p>' + contact}, CFG)
        self.assertEqual([f for f in quiet if f['code'] == 'LINT_TEMPLATE_SIMILARITY'], [])

    def test_the_same_outline_with_different_words_is_still_a_template(self):
        heads = ['Điều cần hỏi trước khi đặt xe', 'Cách tính tiền thuê theo ngày', 'Những khoản dễ bị bỏ sót', 'Cách nhắn tin cho cửa hàng']
        mine = self.article(''.join('<h2>%s</h2><p>Nội dung %d của bài này nói về chuyện khác nhau hoàn toàn.</p>' % (h, i) for i, h in enumerate(heads)))
        other = ''.join('<h2>%s</h2><p>Phần %d viết bằng câu chữ hoàn toàn riêng biệt khác.</p>' % (h, i + 9) for i, h in enumerate(heads))
        found = [f for f in writing.lint(mine, self.TOPIC, FACTS, {'TH-VI-0098': other}, CFG) if f['code'] == 'LINT_TEMPLATE_SIMILARITY']
        self.assertEqual([f['severity'] for f in found], ['fix'])


class EnglishLintTests(unittest.TestCase):
    TOPIC = {'language': 'en', 'primary_keyword': 'weekly motorbike rental'}
    GOOD = ('<h2>Start</h2><p>Renting a motorbike by the week works out differently from renting by the day.</p><h2>Count</h2><p>Count the days you will really ride.</p>'
            '<h2>Ask</h2><p>Ask the shop about pick-up and return times.</p>')

    def article(self, body, **fields):
        base = {'body_html': body, 'title': 'Weekly motorbike rental in Hanoi', 'seo_title': 'Weekly motorbike rental in Hanoi: how to count the days',
                'meta_description': 'How to work out the cost of a weekly motorbike rental against daily and monthly rates, with the questions worth asking first.',
                'focus_keyword': 'weekly motorbike rental', 'business_claims': []}
        base.update(fields)
        return base

    def codes(self, article, severity=None):
        return [f['code'] for f in writing.lint(article, self.TOPIC, FACTS, None, CFG) if severity is None or f['severity'] == severity]

    def test_a_clean_english_article_has_no_fix_level_finding(self):
        self.assertEqual(self.codes(self.article(self.GOOD), 'fix'), [])

    def test_english_generic_anchors_and_provenance_leaks_are_caught(self):
        self.assertIn('LINT_GENERIC_ANCHOR', self.codes(self.article(self.GOOD + '<p><a href="https://rentbikehanoi.com/x/">click here</a></p>')))
        self.assertIn('LINT_SOURCE_NOTE_LEAK', self.codes(self.article(self.GOOD + '<p>As an AI language model, I cannot say.</p>')))

    def test_an_english_price_statement_is_judged_like_a_vietnamese_one(self):
        body = self.GOOD + '<p>Thuê xe máy Nguyễn Hà charges 333,000 VND per day.</p>'
        self.assertIn('LINT_PRICE_NOT_APPROVED', self.codes(self.article(body), 'fix'))
        self.assertEqual([c for c in self.codes(self.article(self.GOOD + '<p>The fine is 600,000 VND.</p>')) if c.startswith('LINT_PRICE') or c == 'LINT_DISCLAIMER_MISSING'], [])


class DeclaringAWaitTests(unittest.TestCase):
    def result(self, waits=(), faults=(), lint=()):
        return {'data_waits': list(waits), 'content_fails': list(faults), 'lint': [{'code': c, 'severity': s} for c, s in lint]}

    def test_a_clean_draft_is_submitted_as_it_is(self):
        self.assertEqual(writing.submission_check(self.result(), None), (True, [], []))

    def test_a_known_fault_is_not_submitted_unless_the_writer_says_so(self):
        ok, problems, _ = writing.submission_check(self.result(faults=['FOCUS_KEYWORD_MISSING']), None)
        self.assertFalse(ok)
        self.assertIn('nothing was submitted', problems[0])
        self.assertTrue(writing.submission_check(self.result(faults=['FOCUS_KEYWORD_MISSING']), None, allow_faults=True)[0])

    def test_a_fix_level_lint_blocks_but_a_consider_level_one_does_not(self):
        self.assertFalse(writing.submission_check(self.result(lint=[('LINT_PADDING', 'fix')]), None)[0])
        self.assertTrue(writing.submission_check(self.result(lint=[('LINT_META_TOO_LONG', 'consider')]), None)[0])

    def test_a_draft_that_depends_on_missing_data_must_say_exactly_what_it_waits_for(self):
        needs = self.result(waits=['FEATURED_MEDIA', 'INTERNAL_LINKS', 'AUTHORITATIVE_INVENTORY'])
        ok, problems, _ = writing.submission_check(needs, None)
        self.assertFalse(ok)
        self.assertIn('--waiting-for FEATURED_MEDIA INTERNAL_LINKS', problems[0])
        self.assertTrue(writing.submission_check(needs, ['FEATURED_MEDIA', 'INTERNAL_LINKS'])[0])
        self.assertEqual(writing.submission_check(needs, ['auto'])[2], ['FEATURED_MEDIA', 'INTERNAL_LINKS'])
        self.assertFalse(writing.submission_check(needs, ['FEATURED_MEDIA'])[0])  # one needed code is missing

    def test_an_offline_inventory_is_never_a_wait_the_writer_must_declare(self):
        self.assertTrue(writing.submission_check(self.result(waits=['AUTHORITATIVE_INVENTORY']), None)[0])
        self.assertEqual(writing.submission_check(self.result(waits=['AUTHORITATIVE_INVENTORY']), ['auto'])[2], [])

    def test_a_wait_the_data_does_not_need_is_refused_and_so_is_an_unknown_code(self):
        ok, problems, _ = writing.submission_check(self.result(), ['INTERNAL_LINKS'])
        self.assertFalse(ok)
        self.assertIn('not needed', problems[0])
        self.assertFalse(writing.submission_check(self.result(), ['SOMETHING'])[0])


if __name__ == '__main__':
    unittest.main()
