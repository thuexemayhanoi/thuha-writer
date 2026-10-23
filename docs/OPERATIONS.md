# Operating ThuHa Writer (bilingual: 500 Vietnamese + 500 English)

All commands run from this repository with `PYTHONPATH=src`. There is no pip
install step. Use Python 3.11+ on Linux. No model API credentials are needed.

## Two ledgers and the hand-over

* **Shared ledger** — the `factory-state` branch (`data/state/factory.json` plus content-addressed
  documents). GitHub Actions read and write it with compare-and-swap (`--remote`). It is operational
  data, never code. `main` stays the source of code and policy.
* **Session ledger** — the same two paths inside a session's own branch (`--git-branch`), used when a
  session cannot write `factory-state` (its REST writes are closed). Nothing reads it. It reaches the
  queue only through `promote`.

```
python3 -m thuha.cli --remote promote                 # the PLAN: FAST_FORWARD / ALREADY_INCLUDED / DIVERGED / ...
python3 -m thuha.cli --remote promote --apply         # performed by the queue job after a merge to main
python3 -m thuha.cli --git-branch sync                # plan: bring the session ledger up to the shared one
python3 -m thuha.cli --git-branch sync --apply        # do it (before a new session starts working)
```

`promote` is **fast-forward only**: the shared ledger's history (events before the schema migration marker)
must be the first part of the session ledger's, nothing may have been written to the shared ledger after its
own migration, every topic/submission/receipt/intent/research request of the shared ledger must still be
there unchanged, and no publisher may hold the ledger. Documents are copied first (immutable and
content-addressed: an existing one is compared and kept, a collision aborts), then the ledger is replaced in
one compare-and-swap that re-plans if the shared ledger moved in between. The stricter of the two `controls`
wins, the shared `inventory_document` and `adapter` pointers are kept, and a `LEDGER_PROMOTION` event records
what was handed over. Running it again changes nothing. A session that kept working on an old copy is
refused (`DIVERGED`), nothing is written, and the remedy is `sync` *before* working.

The schema-4 to schema-5 migration is deterministic (the marker event copies the timestamp of the event it
follows), so the shared ledger and a session ledger can be migrated by different processes and still compare.

## Writers, reviewers, QA

Writers follow [the V5 writer brief](V5-WRITER-BRIEF.md); reviewers [the reviewer brief](V5-REVIEWER-BRIEF.md).

```
python3 -m thuha.cli --git-branch claim --session SESSION --agent-id claude-writer-W1
python3 -m thuha.cli --git-branch kit --topic-id TH-VI-0001 > kit.json     # same-language links, images with that language's alt text
python3 -m thuha.cli --git-branch precheck --topic-id TH-VI-0001 --file article.json
python3 -m thuha.cli --git-branch submit --slot W1 --session SESSION --fence FENCE --file article.json
python3 -m thuha.cli --git-branch review --file review.json --topic-id TH-VI-0001   # THUHA_REVIEWER_ID set; not the writer
python3 -m thuha.cli --remote qa --pending            # reviewed drafts, and READY drafts whose QA predates the policy
```

An actual authorized AI session must do the research and writing; Actions never generate prose. Capture real
public source evidence with `source --url URL` (or `--external-fetch` from an authorized fetcher); if DNS, HTTP
or permissions fail, mark the source blocked — never invent a capture. Intake accepts at most 100 candidates and
checks the complete inventory and every queued intent.

**Article contract.** `topic_id`, `session`, `agent_id`, `source_commit`, `language` (`vi` for `TH-VI-####`, `en-US`
for `TH-EN-####` and legacy `TH-######`), `title`, `body_html`, `seo_title`, `meta_description`, `focus_keyword`,
`canonical`, `category_id`, `featured_media` (an existing image whose alt text is in the article's language),
`sources`, `business_claims`. Submission saves the immutable document first, then its receipt; preserve the
SHA through quota exhaustion. Only changed bytes count as a repair (limit in policy). QA failure never makes an
Actions job rewrite prose.

**Review.** An independent reviewer (never the writer) attests the exact revision: intent, factual accuracy,
originality, business facts, image relevance and — Vietnamese — native language **and** no machine translation,
English — `english` or `native_language`. The review names the article's language. The reviewer roster is in
`config/qa.json`; the identity is attribution, not cryptographic proof, so protect code, policy and the state writer.

**QA** is deterministic and runs on the shared ledger. It never replaces the reviewer. A draft without a recorded
review is *not* evaluated (it would fail only for the missing review and be sent to repair). Vietnamese QA needs an
adapter or authenticated inventory; with a public-only one it reports `BLOCKED`, not `FAIL`.

## Two languages: quota, priority, matrix

```
python3 -m thuha.cli quota                                  # per language: target, live, unresolved, remaining
python3 -m thuha.cli matrix next --language vi --limit 10   # planned topics awaiting sources
python3 -m thuha.cli --remote brief --language vi           # PLANNED topics already admitted
```

`claim` and `refill` serve Vietnamese first; English only when Vietnamese has nothing admissible or needs
nothing more. A language at its ceiling (live + unresolved intents) takes no writers and no publication. Counts
are the inventory's plus the factory posts WordPress confirmed after that inventory was read, so a stale
inventory never lets a language drift past 500. The quota needs an inventory whose `language_source` is
`adapter` (or the committed authenticated snapshot for offline planning); the public REST inventory is labelled
`public-rest-unverified` and refused for counting.

`data/bilingual/matrix/`: `vi500` (500 new) and `en500` (275 protected + 57 queued in the ledger + 168 new).
A row becomes a topic only through `intake`, which needs captured dated sources and an independent intent
review; otherwise it stays `NEEDS_SOURCE`. After the ledger changes, run `scripts/export_queued.py` and
`scripts/build_matrices.py`. Rows retired because a queued topic already covers them are kept in
`data/bilingual/seeds/retired/` with the reason.

## Publisher

```
python3 -m thuha.cli --remote publisher --mode dry-run
python3 -m thuha.cli --remote --output artifacts publisher --mode drain      # the scheduled path
python3 -m thuha.cli --remote publisher --mode production --topic-id TH-VI-0001   # one topic
python3 -m thuha.cli --remote publisher --mode reconcile [--topic-id TH-VI-0001]  # read-only
python3 -m thuha.cli --remote publisher --mode verify [--topic-id TH-VI-0001]     # public-page checks
python3 -m thuha.cli --remote publisher --mode acknowledge --topic-id TH-VI-0001 --note "what was checked"
python3 -m thuha.cli --remote controls --pause on          # or --emergency-stop on
```

**Phases of an intent.** `INTENT` (reserved before the POST) → `PUBLISHED` (WordPress confirmed) or
`NEEDS_RECONCILIATION` (outcome unknown) or `DRAFT_HELD` (WordPress holds a draft) or a closed phase:
`NOT_SENT` (stopped before the POST, or the connection never opened) and `REJECTED` (the plugin refused with a
code that proves nothing was created and a read-back found nothing, or WordPress still had nothing after the
grace period of one hour). Closed phases free their slot; every other phase except `PUBLISHED` counts as a post
and keeps counting.

**What `drain` does, every run.** (1) Reconcile every unresolved intent read-only; a post that exists is
recorded, an absent one inside the grace period is waited for, and while anything stays unresolved the run
stops red. (2) Publish READY topics one at a time inside the release caps, Vietnamese first. A language at its
ceiling is skipped. A topic that can no longer pass QA goes back to repair and the queue moves on; a failure that
touches WordPress and is not clean stops the run. (3) Run public-page checks that are due. The JSON says why a
run stopped; the exit code is 2.

**What decides PUBLISHED.** WordPress returned an ID, status `publish`, the planned permalink in the right
language namespace, and the post carries this intent's owner, key and marker. Then (not before) the adapter
read-back is compared with the reviewed article and the result is kept in the receipt (`integrity`). A
`MISMATCH` opens an alert: no new post is published until `acknowledge`. The public page is checked afterwards;
failures back off (10 min, 30 min, 1 h, 3 h) and end as `FAILED_FINAL` after five attempts. They are shown on
the dashboard and never stop the queue. The first stage's two posts must have passed their public-page check
before the controlled-scale stage can start.

**Never.** No command updates or deletes existing WordPress posts or creates categories; no code POSTs twice
for one intent; nothing clears an intent by hand. All writes go through the companion plugin
([adapter guide](bilingual/ADAPTER.md)); until `adapter-preflight` succeeds the status is
`BLOCKED_ADAPTER_NOT_DEPLOYED`.

## Workflows

* `quality` — tests, matrices, plugin package, validation, dry-run; on `main` also reads the real ledger and prints
  the promotion plan. Triggered by code, config, matrix **and ledger** changes.
* `thuha-ready-publisher` — after a successful quality run on `main`, hourly, or by hand. Jobs: `preflight`
  (read-only, evaluates the release gate); `queue` (no WordPress secret: `promote --apply`, `audit --max-age 18000`,
  `qa --pending --language en`); `protected-publish` (only when the gate is open, inside `thuha-production`:
  adapter preflight, authenticated `audit`, `qa --pending`, `publisher --mode drain`).
* `maintenance` — read-only health every six hours; manual tasks (`audit`, `coordinator`, `refill`, `intake`,
  `qa`, `recovery`, `promote`).
* `publisher` — manual single-topic modes (`dry-run`, `production`, `reconcile`, `verify`, `acknowledge`).

## Go-live (a separate owner decision)

The release lists `languages_enabled` (empty by default). Configure credentials inside the protected
`thuha-production` environment, not by copying another repository's secrets. Keep `main` review + the `quality`
check required; restrict the `factory-state` writer to the Actions app and forbid force pushes. Verify the
WordPress user and the registered Yoast REST fields. Coordinate any other tool publishing to the same site
(`cross_publisher_coordination_verified`). Approve a real pilot reference, reviewer roster and editorial policy
before enabling `config/release.json`. Unit tests do not prove these external controls exist.

Resource use: only read-only health and the hourly queue job run on a schedule; the expensive authenticated
audit runs in the protected job. A stale inventory blocks work and is shown in the dashboard. No scheduled AI
writer exists and production publishing is OFF.

The full public audit is committed. Authenticated SEO metadata is retained separately for the owner and
excluded from this public repository and history. Public focus-keyword values stay UNKNOWN.
