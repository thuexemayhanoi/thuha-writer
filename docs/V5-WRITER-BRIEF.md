# V5 writer brief (read fully before claiming)

You are one authorized Claude writer session for https://rentbikehanoi.com,
operating inside the ThuHa Writer factory. The site goal is 500 English and 500
Vietnamese posts, Vietnamese first: claim returns a Vietnamese topic whenever one
is admitted. Write each article natively in its topic's language; never translate. Work from the repository root with
`export PYTHONPATH=src`. Every state command takes `--git-branch` in this session (REST writes are closed by the proxy; `--remote` is for environments that can write factory-state). The container
cannot reach any website except api.github.com: research with the Parallel
`web_fetch`/`web_search` MCP tools (session_id
`thuha-v5-factory-3la2u4-20261023-aaaaaaaa`, model_name `claude-fable-5-1`).

## Loop

0. Once per session, before claiming: `python3 -m thuha.cli --git-branch sync --apply`. It copies the shared ledger
   (`factory-state`) into this branch so your work starts from what the queue already holds. If it answers `DIVERGED`, stop
   and report: this branch holds work the shared ledger has not got, and the owner decides how to hand it over.
1. `python3 -m thuha.cli --git-branch claim --session <SESSION> --agent-id <AGENT>`
   SESSION is `w<N>-<date>-<random>` (letters, digits, dashes, 4–80 chars),
   AGENT is `claude-writer-W<N>`. Save slot, fence, topic_id from the output.
   If it fails with "No admissible researched topic", stop and report.
2. `python3 -m thuha.cli --git-branch pack --topic-id <TOPIC> --out pack.json` (read-only; `next` shows what can be written now).
   Read the topic record and intent, the category chain and canonical, the shop facts and reference prices, the saved
   sources and the other topics' sources that fit, the live same-language links and archives, the images with alt text in the
   article's language, the existing titles in the same category (do not duplicate them), what the topic is expected to wait for,
   and the rules. Nothing in it is invented: what is missing is listed as missing. `kit` is the older, smaller handoff.
3. Research. The topic's `sources` already carry captured evidence documents
   (`resume --topic-id` or the kit shows them). Read each source URL with
   web_fetch to learn the facts. You may add up to three more sources: fetch
   the page, write a record file
   `{"url","fetcher":"parallel-web-fetch","status":"ok","fetched_at":"<ISO UTC +00:00>","title","content":"<verbatim excerpt text>"}`
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
   featured_media (an id from the kit's featured_media_options whose alt text
   fits; if the kit lists `NEEDS_MEDIA` under `blockers`, write the article anyway, leave `featured_media` null and store it as
   a draft that waits for data, step 7: it cannot pass QA until an image with alt text in that language exists, and nothing may be invented), sources (list of {url, document, supports}; include the topic's own
   sources plus any you captured), business_claims (usually `[]`; if you quote
   a reference price, add {"kind":"reference_price","vehicle":"manual|automatic|electric|50cc|Vision|Air Blade","period":"day|week|month","value_vnd":<int inside the business-facts interval>} and write a sentence containing "reference prices" plus a confirm-before-booking note).
6. `python3 -m thuha.cli --git-branch build --topic-id <TOPIC> --body body.html --meta meta.json` composes `article.json` from the pack
   (topic, session, agent, commit, language, canonical, category, sources are filled in; you write the body, `seo_title`,
   `meta_description`, the chosen `featured_media` and any `business_claims`) and runs the precheck; `precheck --file` runs it on a file you wrote
   yourself. Read `fixes` (where and how to fix each failure) and `lint` (`fix` ones will be refused by `submit`; `consider` ones are judgement
   calls). Fix and re-run until `ready_to_submit` is true and, when nothing is missing, `would_pass_qa` is true (automatic score >=85/100).
   The check changes nothing, so repeat it as often as you need; do not submit a draft you know will fail. No independent AI review is required. Only then:
7. `python3 -m thuha.cli --git-branch submit --slot <SLOT> --session <SESSION> --fence <FENCE> --file article.json`.
   `submit` runs the same check again and refuses (nothing stored, no repair spent) a draft that is known to fail. If `precheck` exits 3 (only
   data is missing: `data_waits` lists `FEATURED_MEDIA`, `INTERNAL_LINKS` and/or `AUTHORITATIVE_INVENTORY`, and `content_fails` is empty), add
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
  Vietnamese title, meta, alt text and links only; regulated claims (giấy phép, bằng lái, mức phạt, visa, đăng kiểm…) need an
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
