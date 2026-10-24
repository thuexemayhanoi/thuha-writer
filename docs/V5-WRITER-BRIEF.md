> **Cập nhật 23/10/2026 (ưu tiên áp dụng):** Ảnh/alt hoàn toàn tùy chọn. Claude không cần xem hoặc tìm ảnh WordPress; `featured_media: null` nộp, QA và xuất bản bình thường, không đợi `FEATURED_MEDIA`. Các mô tả lịch sử dưới đây về bắt buộc ảnh/alt không còn hiệu lực. Xem [quy định mới](MEDIA-OPTIONAL-POLICY.md).

# V5 writer brief — reusable writer steps (read AGENTS.md first)

> **Current 23/10/2026 override:** `AGENTS.md` and `config/qa.json` control the live workflow: QA >=75 and zero hard failures, automatic publishing already enabled within release caps. A writer can select eligible English if Vietnamese lacks verified media/links/source. Do not reuse hardcoded session IDs or assume all sessions have the same network/tools.

> **24/10/2026 rendered-language update:** Follow [bilingual/RENDERED-LANGUAGE-QA.md](bilingual/RENDERED-LANGUAGE-QA.md). Your VI/EN title, SEO title, meta description, focus keyword, body and same-language links must pass source QA before publication. Public page H1, SEO tags and HTML lang are inspected after publication by the publisher; shared UI text such as breadcrumbs, menu, TOC and WordPress global Site Title/Tagline is owned by theme/plugin, **not** by Writer. Keep the current QA ≥75 and existing release cap unchanged.

You are one authorized Claude writer session for https://rentbikehanoi.com,
operating inside the ThuHa Writer factory. The site goal is 500 English and 500
Vietnamese posts **including existing live posts**. Vietnamese is prioritized when a researched claimable topic exists; if VI is blocked by missing real data, EN is allowed. Write each article natively in its topic's language; never translate. Work from the repository root with
`export PYTHONPATH=src`. Use `--git-branch` when this writer can only commit on its own branch; use `--remote` only when the connected session actually has authorized REST writes to `factory-state`. The historical Claude container's network limitations and model/session identifiers are **not** requirements for future sessions. Check current tool availability, use actual verified source fetches, and never fabricate evidence.

## Loop

0. Once per session, before claiming: `python3 -m thuha.cli --git-branch sync --apply`. It copies the shared ledger
   (`factory-state`) into this branch so your work starts from what the queue already holds. If it answers `DIVERGED`, stop
   and report: this branch holds work the shared ledger has not got, and the owner decides how to hand it over.
1. `python3 -m thuha.cli --git-branch claim --session <SESSION> --agent-id <AGENT>`
   SESSION is `w<N>-<date>-<random>` (letters, digits, dashes, 4–80 chars),
   AGENT is `claude-writer-W<N>`. Save slot, fence, topic_id from the output. `next --language vi` ranks what can be written now; add
   `--topic-id <ID>` to claim one of those instead of the next in order (the topic must be claimable and unleased; the claim records that it
   was picked). If it fails with "No admissible researched topic", stop and report.
2. `python3 -m thuha.cli --git-branch pack --topic-id <TOPIC> --out pack.json` (read-only; `next` shows what can be written now).
   Read the topic record and intent, the category chain and canonical, the shop facts and reference prices, the saved
   sources and the other topics' sources that fit, the live same-language links and archives, optional image suggestions in the
   article's language, the existing titles in the same category (do not duplicate them), what the topic is expected to wait for,
   and the rules. Nothing in it is invented: what is missing is listed as missing. `kit` is the older, smaller handoff.
3. Research. The topic's `sources` already carry captured evidence documents
   (`resume --topic-id` or the kit shows them). Read each source URL with
   an actually available trusted web-fetch/research tool to learn the facts. You may add up to three more sources: fetch
   the page, write a truthful record file. Select the **one actually observed** fetcher from the exact allowlist in `src/thuha/research.py` (`parallel-web-fetch`, `claude-webfetch`, or `github-actions-runner`; never invent the label). Example for an actual Parallel fetch:
   `{"url":"<actual URL>","fetcher":"parallel-web-fetch","status":"ok","fetched_at":"<actual ISO UTC +00:00>","title":"<actual title>","content":"<actual sourced excerpt with at least 40 words>"}`
   and run `python3 -m thuha.cli --git-branch source --url <URL> --external-fetch <record.json>`;
   keep the returned `document` sha. Never fabricate a capture. If the article
   text mentions licences, permits, registration, law, visas or embassies, at
   least one source host must end in .gov.vn, .gov, .gov.uk or .gouv.fr.
4. `python3 -m thuha.cli --git-branch heartbeat --slot <SLOT> --session <SESSION> --fence <FENCE>`
   after research and again right before submit (lease is 30 minutes).
5. Write `article.json` with exactly these fields:
   topic_id, session, agent_id, source_commit (current `git rev-parse HEAD`),
   language (the kit's `article_language_value`: "vi" for a TH-VI topic, "en-US" otherwise), title, body_html, seo_title (35–75 chars),
   meta_description (110–180 chars), focus_keyword (the topic's primary
   keyword), canonical (the topic's proposed_url), category_id (the topic's),
   featured_media (optional: null if no verified image ID; no WordPress media/alt lookup, no image wait), sources (list of {url, document, supports}; include the topic's own
   sources plus any you captured), business_claims (usually `[]`; if you quote
   a reference price, add {"kind":"reference_price","vehicle":"manual|automatic|electric|50cc|Vision|Air Blade","period":"day|week|month","value_vnd":<int inside the business-facts interval>} and write a sentence containing "reference prices" plus a confirm-before-booking note).
6. `python3 -m thuha.cli --git-branch build --topic-id <TOPIC> --body body.html --meta meta.json` composes `article.json` from the pack
   (topic, session, agent, commit, language, canonical, category, sources are filled in; you write the body, `seo_title`,
   `meta_description`, the chosen `featured_media` and any `business_claims`) and runs the precheck; `precheck --file` runs it on a file you wrote
   yourself. Read `fixes` (where and how to fix each failure) and `lint` (`fix` ones will be refused by `submit`; `consider` ones are judgement
   calls). Fix and re-run until `ready_to_submit` is true and, when nothing is missing, `would_pass_qa` is true (automatic score >=75/100).
   The check changes nothing, so repeat it as often as you need; do not submit a draft you know will fail. No independent AI review is required. Only then:
7. `python3 -m thuha.cli --git-branch submit --slot <SLOT> --session <SESSION> --fence <FENCE> --file article.json`.
   `submit` runs the same check again and refuses (nothing stored, no repair spent) a draft that is known to fail. If `precheck` exits 3 (only
   data is missing: `data_waits` lists `INTERNAL_LINKS` and/or `AUTHORITATIVE_INVENTORY`, and `content_fails` is empty), add
   `--waiting-for auto` (or name exactly the codes in `submit_waiting_for`). The draft is stored as `WAITING_DATA`: never READY, no QA, the
   slot is freed, and it is claimed again only after `recheck-data` shows the data exists. If `content_fails` is not empty, fix the prose first.
   Record the returned article_sha, then free the slot for the next writer:
   `python3 -m thuha.cli --git-branch release --slot <SLOT> --session <SESSION> --fence <FENCE>`.
   Do not resubmit unless QA later asks for a repair; each changed resubmission
   consumes one of three repairs and goes through a fresh claim of the
   NEEDS_REPAIR topic (read `topic.repair_notes` in the kit first).
8. Report: topic_id, slot, article_sha, word count, sources used, any blocked
   source, automatic QA result and remaining data blockers. Run `qa --pending` for completed submissions; never wait for a reviewer.

## Editorial bar

- Vietnamese topics: native Vietnamese prose for a reader in Vietnam, at least 950 syllables (the QA floor; aim for 1,500–3,000),
  Vietnamese title, meta and links only; images optional; regulated claims (giấy phép, bằng lái, mức phạt, visa, đăng kiểm…) need an
  official `.gov.vn` source; prices only as `giá tham khảo` with a reminder to confirm before booking. The rest of this bar applies
  to both languages.
- English topics: 1,200–2,500 words of original English for an international reader in Hanoi.
  Answer the search intent in the first 150 words. Use `<h2>` sections (at
  least three) and `<h3>` where useful; no `<h1>`; paragraphs in `<p>`; lists
  allowed; a short FAQ `<h2>` with 3–5 `<h3>` questions when genuinely useful.
- Facts come from the captured sources. Attribute them in prose ("the
  Ministry of Public Security page on Decree 168 lists...") and link the
  source URL with a plain `<a href>`; do not paste long quotations.
- Business facts, when relevant: Thuê xe máy Nguyễn Hà, hotline 0334 699 969,
  Ngõ 5 Nguyễn Văn Cừ, Bồ Đề, Long Biên, Hà Nội, open 09:00–21:00 daily.
  Never state delivery, deposit, refund or extension policy; never say
  "no deposit"; never claim firsthand testing or customer stories.
- At least two internal links to URLs from the kit's internal_link_targets (always in the article's own language; a link to the
  other language fails QA), chosen for relevance, with descriptive anchor text. No other same-site URLs.
- No `<script>`, `<style>`, `<meta>`, `<iframe>`, `<form>`, `<img>` without alt,
  no HTML comments, no schema markup (Yoast adds it).
- No slug, canonical or category other than the topic's. Do not mention
  Claude, AI or this factory in the article.
