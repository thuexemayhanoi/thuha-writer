# ThuHa Writer
https://rentbikehanoi.com

**V4 core implemented and tested. WordPress production publishing remains OFF.**

Repository: `thuexemayhanoi/thuha-writer`  
Languages: English (en-US) and original Vietnamese (vi)

Current owner goal: **500 published English blog posts total + 500 Vietnamese blog posts total, Vietnamese first.**

## Current bilingual handoff

Read [AGENTS.md](AGENTS.md), [the verified WordPress handoff](docs/bilingual/HANDOFF.md)
and [the complete Claude instruction](docs/bilingual/CLAUDE-PROMPT.md) first.
Live preparation created 49 categories (27 VI, 22 EN), preserving the 10 existing
categories. IDs, parents and actual URLs are in `data/bilingual/taxonomy-map.csv`.
The fresh snapshot is 275 published EN posts and 0 VI posts: provisionally add
500 VI then 225 EN, recounting live before publishing. Pages do not count.

**This commit prepares taxonomy, snapshots and the implementation brief; the V4
runtime/config still contains the old 2000/en-US assumptions and must be
migrated by the next implementation. Production publishing remains OFF.**
The native VI publisher adapter is not implemented/deployed here. Claude can
complete code, matrix and offline QA using only this repository; live checks
belong to the credentialed publisher. Historical V4 documents below describe
the earlier implementation, not proof of bilingual readiness.

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
7. **Controlled scale** — after bilingual migration, reach 500 published posts per language including existing posts.

Read `docs/PHASE-01-AUDIT.md` and `docs/EXECUTION-ROADMAP.md` before implementing automation.

Current implementation: [V4 architecture and boundaries](docs/V4-IMPLEMENTATION.md).
Measured delivery and blockers: [V4 delivery checkpoint](docs/V4-DELIVERY.md).
Run `PYTHONPATH=src python3 -m unittest discover -s tests -v` and
`PYTHONPATH=src python3 -m thuha.cli --help`. The complete technical inventory
and protected URLs are under `reports/live-audit/`. There is no paid AI API
dependency and no automatic AI prose generation inside GitHub Actions.

**Counting rule:** Historical reports mentioning 107 published posts are not a fresh count. Reconcile directly with WordPress and only attribute articles to an agent when explicit provenance and readback evidence exist.
