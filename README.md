# ThuHa Writer
https://rentbikehanoi.com

**Bilingual workflow implemented and tested offline. WordPress production publishing remains OFF.**

V5 writer-session runtime (merged from the 23 October 2026 session branch): labelled external source
evidence, a read-only writer kit, a non-mutating precheck, source-backed topic admission and the cycle
report. See [V5 writer runtime](docs/V5-WRITER-RUNTIME.md), the [writer brief](docs/V5-WRITER-BRIEF.md)
and the [reviewer brief](docs/V5-REVIEWER-BRIEF.md). Its numbers were measured for the old 2,000-post
goal; the live goal is 500 + 500 (see below). Live inventory on 23 October 2026: 275 published posts,
6 pages, 59 categories.

Repository: `thuexemayhanoi/thuha-writer`  
Languages: English (`en-US`, site root) and original Vietnamese (`vi`, under `/vi/`)

Owner goal: **500 published English blog posts in total and 500 published Vietnamese blog posts in total,
existing posts included, Vietnamese first.** Pages, drafts and trash never count. The old English-only
2,000-post goal is superseded; documents that still mention it are labelled historical.

## Where things stand (read this first)

| Area | State |
|---|---|
| Runtime (state schema 5, per-language quota, Vietnamese-first claim/refill/drain, bilingual QA, publisher, dashboard) | **Implemented, unit-tested offline** |
| Matrices `data/bilingual/matrix/vi500.*` (500 new) and `en500.*` (275 protected + 225 new) | **Built and validated offline; rows are plans, not articles, all `NEEDS_SOURCE`** |
| Companion plugin `wordpress/thuha-native-vi-publisher` + `dist/*.zip` | **Implemented, packaged, run against an offline WordPress simulation** |
| Plugin installed on rentbikehanoi.com, `RBHVI_Language` called for real, Yoast verified | **NOT installed, NOT tested live** (`BLOCKED_ADAPTER_NOT_DEPLOYED`) |
| Source capture, intent review, article writing, independent review | **Not started**: needs real AI sessions and dated sources; nothing is published |
| Live inventory, quota recount, staging post, archive/sitemap checks | **PENDING** with the credentialed publisher |

Published counts in the repo are a snapshot (275 EN, 0 VI at 2026-10-22). They are not a live counter:
the publisher recounts both languages through the adapter before every reservation.

Read [AGENTS.md](AGENTS.md), [the WordPress handoff](docs/bilingual/HANDOFF.md),
[the Claude instruction](docs/bilingual/CLAUDE-PROMPT.md), [the adapter guide](docs/bilingual/ADAPTER.md),
[the matrix guide](docs/bilingual/MATRIX-AUTHORING.md) and [the implementation status](docs/bilingual/IMPLEMENTATION-STATUS.md).

## Commands

```
PYTHONPATH=src python3 -m unittest discover -s tests -v     # 180+ offline tests (PHP harness runs if php exists)
PYTHONPATH=src python3 -m thuha.cli validate                # config, goal 500/500, matrices, adapter package
PYTHONPATH=src python3 -m thuha.cli matrix next --language vi --limit 10   # next topics to research (read-only)
PYTHONPATH=src python3 -m thuha.cli quota                   # per-language target / live / unresolved / remaining
python3 scripts/build_matrices.py                           # rebuild + validate the matrices from seeds
python3 scripts/build_adapter_zip.py                        # rebuild the reproducible plugin ZIP
php tests/php/run.php                                       # plugin logic against the WordPress simulation
```

## Mission

Create an original WordPress editorial factory, informed by architectural study of `thuexemayhanoi/wp-writer`, rather than copying its operational state, code or domain-specific policies. First reconcile the existing WordPress site; then build small, testable components.

## Safety invariants

- No WordPress writes, scheduled publishing or workflow auto-runs in Phase 1.
- Existing WordPress posts, pages, published URLs, canonicals and category ancestry are authoritative. Do not assume an empty site or restart the count.
- Detect duplicates by WordPress ID, canonical, slug, primary search intent and editorial similarity before planning or writing.
- Do not delete or rewrite live posts, canonical, title, Yoast metadata, taxonomy, menus or theme without separate approval.
- Never fabricate sources, testimonials, laws, prices, business claims or field experience. Facts must be traceable.
- An uncertain taxonomy match, content claim or post-publication state results in `NEEDS_REVIEW`, not a guessed action.
- Publishing will require owner approval, an isolated credential environment, immutable receipts, readback verification, and idempotent retries.
- GitHub Actions can coordinate W1–W9 slots and run code, but cannot independently generate new AI articles without a real external AI execution session or authorized service.
- No secrets, authentication tokens, application passwords, user data or confidential exports may be committed. The repo is currently public.
- Do not copy any production domain, category ID, API credential, publication ledger, or repository-specific runner condition from the reference project.

## Project stages

1. **Audit & baseline** — read reference code and real WordPress; document gaps, risks and safeguards.
2. **Inventory-only tooling** — safely inspect all existing posts/pages/taxonomy and generate timestamped reproducible reports.
3. **Topic research + intent mapping** — grounded source checks, deduplication, existing category matching, topic queue.
4. **W1–W9 coordinator** — lease/heartbeat/atomic claim, durable checkpoints, source and submission receipts.
5. **Quality gates** — factual validation, useful original writing in each language, metadata, image, links, taxonomy, intent, accessibility and QA.
6. **Publisher pilot** — owner-controlled enablement, small batches, isolated WordPress credentials, post-publish verification and recovery.
7. **Controlled scale** — reach 500 published posts per language including existing posts, Vietnamese first, each language capped independently.

Read `docs/PHASE-01-AUDIT.md` and `docs/EXECUTION-ROADMAP.md` before implementing automation.

Architecture: [V4 architecture and boundaries](docs/V4-IMPLEMENTATION.md) (bilingual deltas at its end).
Historical English-only checkpoint (superseded goal): [V4 delivery](docs/V4-DELIVERY.md).
Run `PYTHONPATH=src python3 -m thuha.cli --help`. The complete technical inventory
and protected URLs are under `reports/live-audit/`. There is no paid AI API
dependency and no automatic AI prose generation inside GitHub Actions.

**Counting rule:** Historical reports mentioning 107 or 273 published posts are not a fresh count. Count distinct published post IDs per native language through the adapter, include existing posts, exclude pages/drafts/trash, count an unknown publication outcome as if it had published, and only attribute articles to an agent when explicit provenance and readback evidence exist.
