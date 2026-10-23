# ThuHa Writer: instructions for AI sessions

## Current owner brief — 2026-10-23 UTC

Target only `https://rentbikehanoi.com`, repository `thuexemayhanoi/thuha-writer`.
Read `docs/bilingual/HANDOFF.md`, `docs/bilingual/CLAUDE-PROMPT.md`,
`docs/bilingual/IMPLEMENTATION-STATUS.md` and `data/bilingual/plan.json` first. The goal is
**500 published English posts and 500 published Vietnamese posts on the site, existing posts included, Vietnamese
first**. The old English-only 2,000-post goal is superseded and every document that still says 2,000 is historical.
The V4 runtime is migrated (state schema 5, per-language quota, Vietnamese-first claim/refill/drain, bilingual QA,
adapter-only publishing) and the V5 writer-session work (nine drafts, 57 admitted English topics, sources, reviews,
history) is merged and preserved. Authenticated snapshot: 275 EN + 0 VI; 225 EN + 500 VI still missing, of which 57 EN are
already admitted to the ledger. Reconcile before each publish reservation; snapshots are not a live counter.

Claude is GitHub-only. WordPress/crawler access is NOT a prerequisite for code, matrix, drafting or offline QA. Use
committed evidence and mark live checks PENDING. Never claim live QA was completed without an actual receipt. The
credentialed publisher owns live reconciliation and post-publication checks. The theme (1.4.0) and the native
Vietnamese plugin (1.1.1) are outside this repository: do not change, version or deploy them from here.

## Queue and publication contract (enforced in code; do not weaken)

- **Two ledgers, one hand-over.** Actions read `factory-state` (`GitStore`). A session that can only push its own branch
  keeps a session ledger in that branch (`--git-branch`, `data/state/factory.json` + `data/documents/`). Nothing reads that
  copy until `promote` moves it into `factory-state`: **fast-forward only** (every event of the shared ledger must be in the
  session ledger in the same order), documents first, one compare-and-swap, idempotent, never an overwrite; a session never
  carries intents or receipts (only the publisher writes them). A diverged ledger is refused with nothing written, and work
  done on a stale copy cannot be merged automatically. Run `--git-branch sync --apply` before a new session works, so its
  ledger starts from the shared one; hand-over works repeatedly (sync, work, promote). The queue job runs `promote --apply` after every merge to `main`; nothing here runs it against the real
  ledger from a session.
- **QA before publication, review before QA.** `qa --pending` evaluates a draft only once an independent review is recorded
  (otherwise it would fail for the missing review alone and be sent to repair), and again every READY draft whose report
  predates the current policy. Vietnamese QA needs an adapter or authenticated inventory. English reviews recorded before
  schema 5 (which attest `english`) stay valid for English only.
- **PUBLISHED means WordPress said so.** The intent becomes PUBLISHED when WordPress returns a valid ID, status `publish` and
  the planned permalink for the post this intent created. Stored-content differences (adapter read-back) are recorded in the
  receipt and raise an alert that stops *new* posts until a person acknowledges it. The public-page crawl is a separate step
  with back-off and five attempts; it reports warnings and never blocks the queue.
- **Unknown outcome: reconcile, never POST again.** After a lost answer the publisher reads by idempotency key at once and on
  every run. Only a connection that never opened (`not_sent`), a refusal proven to have created nothing, or an intent absent
  from WordPress after the grace period closes an intent and frees its slot. A draft WordPress holds is never counted and
  never re-sent. Unresolved intents stop the drain (red run) until reconciled.
- **The queue is not blocked by one topic.** A READY topic that can no longer pass QA goes back to repair; the drain moves on.
- Production stays OFF: `config/release.json` is changed only by a reviewed go-live decision, never by a session.

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
python3 scripts/export_queued.py && python3 scripts/build_matrices.py && python3 scripts/build_adapter_zip.py   # then `git diff --exit-code`
python3 scripts/offline_dashboard.py                                      # refresh reports/bilingual if the ledger or counts changed
```
