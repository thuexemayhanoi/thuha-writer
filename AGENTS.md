# ThuHa Writer: instructions for AI sessions

## Current owner brief — 2026-10-22 UTC / 2026-10-23 Vietnam

Target only `https://rentbikehanoi.com`, repository `thuexemayhanoi/thuha-writer`.
Read `docs/bilingual/HANDOFF.md`, `docs/bilingual/CLAUDE-PROMPT.md`,
`docs/bilingual/IMPLEMENTATION-STATUS.md` and `data/bilingual/plan.json` first. This brief
supersedes the old **English-only, 2,000-post goal**. The V4 runtime has been migrated to it
(state schema 5, per-language quota, Vietnamese-first claim/refill/drain, bilingual QA,
adapter-only publishing); anything that still says 2,000 or en-US-only is historical and must
carry a label. Keep code, config, tests, reports and workflows consistent when you change behavior.

The new final site goal is **500 published English blog posts total and 500
published Vietnamese blog posts total**, including existing posts, excluding
pages/drafts/trash. Prioritize Vietnamese. Authenticated snapshot measured
275 EN + 0 VI; provisional additions are 500 VI + 225 EN. Reconcile before each
publish reservation; snapshots are not a live counter.

Claude is GitHub-only. WordPress/crawler access is NOT a prerequisite for code,
matrix, drafting or offline QA. Use committed evidence and mark live checks
PENDING. Never claim live QA was completed without an actual receipt. The
credentialed publisher owns live reconciliation and post-publication checks.

## Language contract (enforced in code; do not weaken)

- English stays at the site root; Vietnamese posts live at `/vi/{ascii-slug}/`, categories at
  `/vi/chuyen-muc/{slug}/`. Topic IDs are `TH-VI-####` / `TH-EN-####` (legacy `TH-######` is English).
- A topic, its category path, URL, article `language` (`vi` / `en-US`), title, meta, alt text, body
  links, review and receipt all carry one language. Cross-language body links are a hard fail;
  hreflang only for a genuinely equivalent pair that already exists.
- Quota is per language: `config/project.json goal.targets` (500/500). Count = live published
  posts from an **adapter** inventory + unresolved intents. Pages, drafts, trash are excluded; the
  public REST collection is not trusted for Vietnamese. 499 -> 500 is allowed, 500 -> 501 never.
- Vietnamese is claimed, refilled, QA'd and drained first; English is not blocked when no
  Vietnamese topic is researched. Each language stops at its own ceiling.
- All writes go through `thuha-native-vi-publisher` (`src/thuha/adapter.py`, `wordpress/`): draft with
  marker, `RBHVI_Language::set_vi`, SEO, verify, publish; replay by idempotency key; never a core
  `/wp/v2/posts` write. Live deployment is unverified until `adapter-preflight` passes.
- Matrix rows (`data/bilingual/matrix/`) are plans. They stay `NEEDS_SOURCE` until dated primary
  sources are captured; never fabricate a crawl, source, price, rule or demand figure.

## Editorial and SEO invariants

- Native original prose for each readership; no automatic translation,
  no duplicate article imports, no paid model API dependency.
- Existing English posts, slugs, titles, canonicals, category ancestry and
  content remain authoritative. Do not rewrite, delete or reparent them.
- A VI article needs the native plugin language marker, not merely Vietnamese
  text or a VI category. Read the adapter contract in the handoff.
- Parent/child category IDs and real URLs already exist in the manifest.
  No category creation by the article publisher; do not copy source-site IDs.
- One primary category and distinct search intent per new article. Compare
  against static pages as well as posts; do not compete with the homepage or
  service pages using repeated main-keyword articles or ward doorway pages.
- Hreflang pairs only for genuinely equivalent pages. Independent VI articles
  use their own canonical and can be indexed without an English pair.
- Do not invent prices, legal rules, inventory, opening hours, firsthand
  experience, customer stories, availability or guarantees. Use evidence.

## Workflow and credentials

Preserve durable leases, fences, checkpoints, immutable submission/review
receipts, bounded repair, idempotency and reconciliation after unknown outcomes.
No blind POST retries. No tokens, application passwords or private SEO exports
in repository files, issue bodies, logs or prompts. Reference repos are
read-only structural inspiration; do not import their code, live ledgers or
business identity. The source topic exports here are **candidate ideas**, not
approved articles, current facts, existing target posts or publish receipts.

Implementation and offline checks are authorized now. Existing production
publisher remains OFF while this is prepared; do not turn it on by changing
`config/release.json`, secrets, reviewer policy or repository protections. Make
the implementation and installable adapter concrete and reviewable first, and
report any deployment needs truthfully. Do not ask the nontechnical owner to
register crawlers or run terminal commands to unblock offline work.

Update README, operating docs and this file when behavior changes. Record the
exact commit, completed checks, next resumable task and unresolved live checks
before quota exhaustion: `docs/bilingual/IMPLEMENTATION-STATUS.md` is that record.

## Checks before any push

```
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m thuha.cli validate
php tests/php/run.php
python3 scripts/build_matrices.py && python3 scripts/build_adapter_zip.py   # then `git diff --exit-code`
```
