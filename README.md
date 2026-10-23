# ThuHa Writer
https://rentbikehanoi.com

**Bilingual workflow and shared queue implemented and tested offline. WordPress production publishing remains OFF.**

The nine English drafts, their sources, the two reviews and the whole history written by the V5 writer session are merged
into this repository (`data/state/factory.json` and `data/documents/`) and a controlled, append-only hand-over
(`promote`) moves them into the ledger that GitHub Actions read (`factory-state`) once this branch is merged. From
there the queue job runs QA and, only when go-live is enabled, the protected job publishes. See
[how a draft becomes a post](#from-draft-to-published-post) and [what must be set up once](#set-up-once-for-automatic-operation).
V5 documents: [writer runtime](docs/V5-WRITER-RUNTIME.md), [writer brief](docs/V5-WRITER-BRIEF.md), [reviewer brief](docs/V5-REVIEWER-BRIEF.md).
Live inventory on 23 October 2026: 275 published posts, 6 pages, 59 categories.

Repository: `thuexemayhanoi/thuha-writer`  
Languages: English (`en-US`, site root) and original Vietnamese (`vi`, under `/vi/`)

Owner goal: **500 published English blog posts in total and 500 published Vietnamese blog posts in total,
existing posts included, Vietnamese first.** Pages, drafts and trash never count. The old English-only
2,000-post goal is superseded; documents that still mention it are labelled historical.

## Where things stand (read this first)

| Area | State |
|---|---|
| Runtime (state schema 5, per-language quota, Vietnamese-first claim/refill/drain, bilingual QA, publisher, dashboard) | **Implemented, tested offline** |
| Nine V5 English drafts + 57 admitted English topics (44 planned, 13 started) | **Merged, ledger preserved byte for byte; NOT yet in `factory-state`** (the hand-over runs after merge) |
| Hand-over `promote` / `sync` (fast-forward only, never overwrites, idempotent) | **Implemented; tested against the real session ledger and the 2026-10-23 snapshot of `factory-state`, never run against the real one** |
| Publisher: PUBLISHED when WordPress returns a valid ID, status and permalink; public-page crawl is a warning step that never blocks | **Implemented, tested end to end against a simulated WordPress** (network faults, repeated runs, two publishers at once) |
| Matrices: `vi500` (500 new) and `en500` (275 protected + 57 queued in the ledger + 168 new) | **Built and validated offline; rows are plans, not articles, all `NEEDS_SOURCE`** |
| Companion plugin `wordpress/thuha-native-vi-publisher` 1.0.0 + `dist/*.zip` | **Implemented, packaged, run against an offline WordPress simulation** |
| Plugin installed on rentbikehanoi.com, `RBHVI_Language` called for real, Yoast verified | **NOT installed, NOT tested live** (`BLOCKED_ADAPTER_NOT_DEPLOYED`) |
| Theme 1.4.0 and `rentbikehanoi-native-vi` 1.1.1 | **Untouched and not in this repository**; the adapter does not pin their versions |
| Vietnamese topics, drafts, reviews | **10 topics admitted and 10 drafts stored as `WAITING_DATA`** (`drafts/vi/`): complete text, first-party facts only, **not READY, no QA, no review, none published**. They wait for an image with Vietnamese alt text, live Vietnamese pages to link to, and an authoritative inventory. 490 Vietnamese rows remain plans |
| Drafts that wait for data (`WAITING_DATA`, `recheck-data`, `drafts/`) | **Implemented, tested offline**; the credentialed publisher's audit clears a wait only when the inventory really holds the data |
| Independent review of the English drafts | 2 of 9 reviewed (TH-000005, TH-000006; both pass QA again under the new policy); the other 7 wait for a reviewer (TH-000002 is under a writer lease that expires and returns it to the queue) |
| Live inventory, quota recount, staging post, archive/sitemap checks | **PENDING** with the credentialed publisher |

Published counts in the repo are a snapshot (275 EN, 0 VI at 2026-10-22). They are not a live counter:
the publisher recounts both languages through the adapter before every reservation. **Nothing is published by this
repository today and nothing will be until the owner enables the release.**

Read [AGENTS.md](AGENTS.md), [the WordPress handoff](docs/bilingual/HANDOFF.md),
[the Claude instruction](docs/bilingual/CLAUDE-PROMPT.md), [the adapter guide](docs/bilingual/ADAPTER.md),
[the matrix guide](docs/bilingual/MATRIX-AUTHORING.md) and [the implementation status](docs/bilingual/IMPLEMENTATION-STATUS.md).

## From draft to published post

```
writer session            claim -> kit -> source -> precheck -> submit        (session ledger: data/state + data/documents)
independent reviewer      resume -> review                                    (a different identity; cannot review its own draft)
merge to main             quality workflow runs, then the scheduled workflow starts
queue job (no WordPress secret)
                          promote --apply      session ledger -> factory-state, fast-forward only, documents first
                          audit --max-age      refresh a stale public inventory
                          qa --pending --language en
protected job (only if release.json is fully enabled; environment thuha-production)
                          adapter-preflight -> audit (authenticated, both languages) -> qa --pending
                          publisher --mode drain:
                            1 reconcile every unresolved intent (read-only; the POST is never repeated)
                            2 publish READY topics, Vietnamese first, inside the release caps and the 500-per-language ceiling
                            3 public-page checks that are due (warnings, back-off, never block)
```

A post is recorded as **PUBLISHED** the moment WordPress answers with a valid ID, status `publish` and the planned
permalink for the intent that created it. What WordPress stored (body, title, SEO fields, category, language marker) is
compared with the reviewed article and recorded with the receipt; a difference raises an alert that stops *new* posts until a
person acknowledges it. The public page (canonical, title, meta, `<html lang>`, schema, no `noindex`) is checked afterwards
with back-off and five attempts: its failures are warnings on the dashboard and never stop the queue. An answer to the POST
that is lost is reconciled by idempotency key at once and on every run; the POST is never sent twice. A draft that WordPress
holds is never counted and never re-sent.

## Set up once for automatic operation

Nothing below is done by this repository, and none of it can be checked offline.

1. **Review and merge this branch.** The merge starts the quality workflow and then the queue job, which hands the nine drafts over.
2. **Protect the branches**: `main` needs one review and the `quality` check; `factory-state` must accept writes only from the
   GitHub Actions app and forbid force pushes (the publisher refuses to run otherwise).
3. **Environment `thuha-production`** with required reviewers, secrets `THUHA_WP_USER` and `THUHA_WP_APPLICATION_PASSWORD` (an
   Application Password of an account that may publish posts), `THUHA_GITHUB_SECURITY_TOKEN` (read access to branch protection)
   and the variable `THUHA_GO_LIVE_APPROVAL`.
4. **Install `dist/thuha-native-vi-publisher-1.0.0.zip`** on WordPress and run `adapter-preflight`. The person or AI with WordPress
   access previews and deploys it; theme 1.4.0 and plugin 1.1.1 stay as they are.
5. **Images with alt text in the article's own language.** An article may only use an existing image whose alt text is in its
   language. Only 15 images carry (English) alt text today, so no Vietnamese article can pass QA until at least one image whose
   alt text is Vietnamese (it must contain Vietnamese letters) is added to the media library. The inventory now lists the whole library.
6. **Reviews.** Seven English drafts need an independent review (`claude-editorial-reviewer` is the only trusted reviewer in `config/qa.json`; the owner confirms or replaces it. The identity is a declared string, not an authenticated person: protect who may write the shared ledger and the policy before trusting it for production); Vietnamese drafts do not exist yet.
7. **Go-live** is one reviewed change to `config/release.json` (`enabled`, `approved`, `approval_ref`, `paused: false`,
   `cross_publisher_coordination_verified`, `languages_enabled`). The first stage publishes at most two posts. Nothing in this
   repository does this.

## Commands

```
PYTHONPATH=src python3 -m unittest discover -s tests -v     # 327 offline tests (the PHP harness runs if php exists)
PYTHONPATH=src python3 -m thuha.cli validate                # config, goal 500/500, matrices, adapter package
PYTHONPATH=src python3 -m thuha.cli --remote promote        # PLAN of the hand-over; add --apply to perform it (queue job only)
PYTHONPATH=src python3 -m thuha.cli --git-branch sync       # session branch: bring the session ledger up to the shared one first
PYTHONPATH=src python3 -m thuha.cli --remote qa --pending   # QA for reviewed drafts and stale READY ones
PYTHONPATH=src python3 -m thuha.cli --remote publisher --mode drain     # reconcile, publish, check (needs the release gate)
PYTHONPATH=src python3 -m thuha.cli matrix next --language vi --limit 10   # next topics to research (read-only)
PYTHONPATH=src python3 -m thuha.cli quota                   # per-language target / live / unresolved / remaining
python3 scripts/build_matrices.py                           # rebuild + validate the matrices from seeds
python3 scripts/export_queued.py                            # refresh the queued English topics from the ledger, then rebuild
python3 scripts/build_adapter_zip.py                        # rebuild the reproducible plugin ZIP
python3 scripts/offline_dashboard.py                        # reports/bilingual/dashboard.* from the committed ledger and snapshots
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
