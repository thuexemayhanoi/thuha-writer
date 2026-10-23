# CURRENT WRITER CONTRACT — 23 October 2026 (supersedes older instructions)

**Scope:** only `thuexemayhanoi/thuha-writer` → `https://rentbikehanoi.com`. This section is the entry point for any fresh Claude/ChatGPT Work session. Never carry a GitHub owner, model, session ID, site address, WordPress secret or ledger from another workflow.

- **Current mechanics:** External AI sessions write researched articles; Actions only run QA, queue and the WordPress publisher. Both Vietnamese (native `vi`, posts under `/vi/`) and English (`en-US`, site root) use automated **QA >=75/100 inclusive**, with **zero hard failures**. No independent AI review or per-post manual approval. `config/qa.json` is the source of truth.
- **Production:** A separate owner-approved release currently has `enabled=true`, `approved=true`, `paused=false`, `stage=auto-scale`, maximum **50 posts/day**. Publication still requires fresh authenticated WordPress inventory, real media/alt, source evidence, internal links, native adapter, language/taxonomy/duplicate checks, idempotent receipts. No GitHub Environment/reviewer or `THUHA_GO_LIVE_APPROVAL`; WordPress credentials live exclusively in **repository GitHub Actions Secrets**.
- **Verified checkpoint only, not live counters:** `factory-state` ledger version 448 on 23 Oct 2026: **9 English PUBLISHED receipts**, **0 READY**, **51 EN and 14 VI PLANNED**, **7 EN and 21 VI WAITING_DATA**, **11 VI HELD**, **0 active leases**. GitHub quality and guarded publisher runs at that checkpoint both succeeded. Read the shared ledger anew before quoting progress or assuming topics remain free.
- **Writer workflow:** identify the active repo/account and read `AGENTS.md`, `docs/bilingual/CLAUDE-PROMPT.md`, `docs/V5-WRITER-BRIEF.md`. If working on a branch-based session ledger, **`--git-branch sync --apply` BEFORE claim**, then `next` → `claim` (or `claim --topic-id` to choose a truly eligible EN/VI topic) → `pack` → real source research → `build`/`precheck` → `submit` → commit and safely hand over with `promote` via the normal main/Actions route. Use `--remote` only where the connected session actually has scoped `factory-state` REST write permissions. A draft committed to a writer branch is **not** visible to the publisher until hand-over. Do not manually overwrite `factory-state`.
- **No false blockers:** Vietnamese is **priority**, not an instruction to finish all 500 VI before writing any English. If an eligible VI article cannot yet obtain a Vietnamese-alt featured image, verified same-language content link, authoritative inventory or source, retain its honest `WAITING_DATA`/`NEEDS_SOURCE` record and work on another eligible topic. Never fake or borrow unrelated media, URL, references or business facts. `HELD` stays held. `W1–W9` are logical slots, NOT running AI agents; maintain and renew a valid lease. Do not depend on another chat's hardcoded session IDs, tool names or model labels.
- **Owner-only facts:** Do not make up deposits, return policies, surcharges or business claims. `docs/bilingual/OWNER-QUESTIONS.md` is a fact checklist for topics that need those claims, **not** a human approval gate for unrelated source-backed articles.
- **Documentation precedence:** current `AGENTS.md` + `config/qa.json` + `config/release.json` + newest `factory-state` status > current writer brief > historical V4/V5 / reference adaptation logs. An older statement about QA85, protected environments, needing reviewer, release OFF, specific Claude session ID or uninstalled adapter is historical, not an active instruction. All previously committed article/source/receipt records remain immutable.

---

> **Owner-policy note (retained for history) — 23/10/2026:** For `rentbikehanoi.com` and `thuexemayhanoi/thuha-writer` only, automatic QA **>=75/100 PASS**, **<75 FAIL**; any hard failure still blocks. Follow `/wp-aiwriter`'s event-driven architecture, NOT its score (76), URLs, credentials, taxonomy or ledger. Both VI and EN use `config/qa.json`. On a policy change, previously READY drafts must pass fresh QA before publisher. PASS moves to the existing queue without human article review. A separate 23/10/2026 owner change has now **enabled auto-scale in `config/release.json` (50/day)**; this QA75 change does not alter that release. WordPress publishing still requires configured repository Secrets, native adapter, verified live inventory, duplicate checks and durable receipts. Confirm success from real WordPress readback, not merely enabled flags. See `docs/AUTO-QA85-PUBLISHER.md` (legacy filename). This paragraph overrides every old QA85 mention below.

# ThuHa Writer: instructions for AI sessions

## Current owner brief — 2026-10-23 UTC

Target only `https://rentbikehanoi.com`, repository `thuexemayhanoi/thuha-writer`.
Owner-confirmed extension policy (23 October 2026): **20,000 VND per hour; more than 6 hours is charged as one rental day**.
Use `config/business-facts.json extension_policy`; this is confirmed, not an unknown policy. Do not change `>6` to `>=6`,
use 30,000 VND/hour or invent another threshold. Before submitting affected drafts, recapture first-party evidence from
the updated facts file and reference the new immutable snapshot; do not rewrite old documents, QA reports or receipts.
Latest owner instruction (23 October): **remove the independent AI article-review gate**.
The active route is writer -> automatic QA >=75/100 + duplicates + correct category/language -> publisher.
Completed drafts go straight to QA; never wait for or fabricate a reviewer. Historical reviews stay immutable.
Hard failures, evidence, real media/links, release configuration, credentials and idempotency still apply.
The owner has requested automatic publication; do not ask for the same content-review approval again.
Do not claim the live queue is enabled until the running branch, adapter and credentialed preflight prove it.
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
  ledger starts from the shared one; hand-over works repeatedly (sync, work, promote). A session that kept working after the shared ledger moved on is `DIVERGED`: `sync` lists its
  `unpromoted` drafts and only `sync --apply --discard-unpromoted` (never automatic, refused while a lease is held) replaces the ledger; each listed draft is then claimed
  and submitted again from its stored document (`scripts/replay_unpromoted.py`: through the normal gates, never around them). The queue appends events whenever it publishes, so run that
  recovery as late as possible and push right after it. The queue job runs `promote --apply` after every merge to `main`; nothing here runs it against the real
  ledger from a session.
- **Automatic QA before publication; no independent AI review gate.** `qa --pending` evaluates every DRAFT_READY submission
  and every READY draft whose policy or article hash is stale. Score = raw automatic points / 80 * 100; threshold 75 (inclusive).
  Any hard failure blocks publication regardless of score. Vietnamese QA needs an adapter or authenticated inventory.
  Legacy review records neither gate QA nor add points; no synthetic attestation may replace them.
- **QA never blames the article for data the site lacks.** An unusable inventory (stale, incomplete, public-only for Vietnamese)
  makes `run_qa` refuse: nothing is evaluated, recorded or changed and `qa --pending` exits 2. A finished draft that would pass
  as written once pages it already links to are live is `BLOCKED_DATA` (stays DRAFT_READY, frees its writer slot, no repair spent,
  not a pass, checked again every run, passes by itself; `claim --revise` lets a writer re-point its links, not a repair). Real faults, typo links, too few links, an image not chosen and a score that stays below 75
  go to repair. `precheck` uses the same classifier (`src/thuha/datawait.py`); `submit` refuses an empty `featured_media` unless
  the draft is stored with `--waiting-for FEATURED_MEDIA`.
- **Event-driven, with the hourly run as fallback.** On the shared ledger `submit` evaluates a completed draft at once and a pass
  dispatches `thuha-qa-ready`; a `WAITING_DATA` draft, a draft over its repair limit and a session ledger in a branch never do. An
  expired inventory is refreshed from the public site (GET only) before a write-capable command; if the site cannot be reached QA
  refuses the old one and records nothing. Topic admission needs no reviewer (a negative verdict or a stale-inventory claim still
  blocks). The publisher checks that it runs from `main` and that the `main` and `factory-state` refs exist (owner change, 23 October).
- **PUBLISHED means WordPress said so.** The intent becomes PUBLISHED when WordPress returns a valid ID, status `publish` and
  the planned permalink for the post this intent created. Stored-content differences (adapter read-back) are recorded in the
  receipt and raise an alert that stops *new* posts until a person acknowledges it. The public-page crawl is a separate step
  with back-off and five attempts; it reports warnings and never blocks the queue.
- **Unknown outcome: reconcile, never POST again.** After a lost answer the publisher reads by idempotency key at once and on
  every run. Only a connection that never opened (`not_sent`), a refusal proven to have created nothing, or an intent absent
  from WordPress after the grace period closes an intent and frees its slot. A draft WordPress holds is never counted and
  never re-sent. Unresolved intents stop the drain (red run) until reconciled.
- **The queue is not blocked by one topic.** A READY topic that can no longer pass QA goes back to repair; the drain moves on.
- Publication is requested by the owner. The separate release on `main` is currently enabled (auto-scale cap 50/day, 23/10/2026). This QA75 change does not modify `config/release.json`; real publishing remains conditional on preflight, adapter, inventory and verified WordPress readbacks. Do not claim success without receipts.
- **A draft may wait for data, never fake it.** A finished text that lacks an image with Vietnamese alt text, live same-language links or an
  authoritative inventory is stored with `submit --waiting-for` as `WAITING_DATA`: never READY, never QA-passed, no media ID, source,
  permalink or check result invented, shared English alt text never edited to help it pass. `recheck-data` (credentialed inventory only)
  clears a wait; completing the draft then goes through automatic QA. Drafts are exported to `drafts/`. Waiting drafts must not link to each other in a loop: QA fails a link to a page that is not live, so a draft links only to drafts written
  before it (`next` reports `planned_link_cycles`, `precheck`/`build` report `link_cycle`). Revising or finishing a
  stored `WAITING_DATA` draft is not a repair, and `promote` accepts it (any other replaced draft must have spent one).

- **Write from the pack, check before storing.** `next` ranks what can be written now (HELD topics are never offered, and a topic that
  needs an official page nobody has read is not offered as writable). `pack --topic-id` assembles what the repository already holds
  (intent, category chain, canonical, shop facts and reference prices, still-current saved sources, live same-language links and images,
  metadata bands, a skeleton with the lease); `build` composes the article from it and runs the non-mutating precheck. `config/writing.json`
  holds the shared bands, templates and fix hints. The advisory lint (`src/thuha/writing.py`) never adds or removes a point and never changes a
  hard failure. `submit` refuses (nothing stored, no repair spent) a draft the precheck knows is faulty, or one that waits for data it did not
  declare, or declares a wait for data that exists; `--waiting-for auto` declares exactly what is missing, `--allow-faults` stores a faulty draft on purpose.
  `claim` keeps its order (Vietnamese first); `claim --topic-id ID` takes one claimable, unleased topic in a language below its ceiling instead, and the
  claim event records `picked`, so a topic nobody can finish here does not stand in front of the ones that can be written.

## Language contract (enforced in code; do not weaken)

- English stays at the site root; Vietnamese posts live at `/vi/{ascii-slug}/`, categories at
  `/vi/chuyen-muc/{slug}/`. Topic IDs are `TH-VI-####` / `TH-EN-####` (legacy `TH-######` is English).
- A topic, its category path, URL, article `language` (`vi` / `en-US`), title, meta, alt text, body
  links and receipt all carry one language. Cross-language body links are a hard fail;
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

Implementation and offline checks are authorized now, including the owner's removal of the AI reviewer gate.
The owner enabled auto-scale separately on 23/10/2026; this QA75 branch does not modify that release. Real publishing requires adapter access and verified WordPress receipts.
Do not bypass credentials or repository protections, invent a verified preflight, or merge/deploy as part of a status check.
Make the implementation and installable adapter concrete and report deployment needs truthfully. Do not ask the nontechnical owner to
register crawlers or run terminal commands to unblock offline work.

Update README, operating docs and this file when behavior changes. Record the
exact commit, completed checks, next resumable task and unresolved live checks
before quota exhaustion: `docs/bilingual/IMPLEMENTATION-STATUS.md` is that record.

## Checks before any push

```
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m thuha.cli validate
php tests/php/run.php
python3 scripts/export_queued.py && python3 scripts/export_drafts.py && python3 scripts/build_matrices.py && python3 scripts/build_adapter_zip.py   # then `git diff --exit-code`
python3 scripts/offline_dashboard.py                                      # refresh reports/bilingual if the ledger or counts changed
```
