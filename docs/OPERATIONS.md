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

`promote` is **fast-forward only**: every event of the shared ledger must also be in the session ledger, in the same
order (events are compared on what they say, not on the hash chain, so a ledger that was migrated or promoted in between
still compares), every topic/submission/receipt/intent/research request of the shared ledger must still be there
unchanged, no publisher may hold the ledger (an expired lease does not count), and the session ledger may not carry an
intent or a receipt that the shared one lacks or changed (only the publisher writes those). Documents are copied first
(immutable and content-addressed: an existing one is compared and kept, a collision aborts), then the ledger is replaced in
one compare-and-swap that re-plans if the shared ledger moved in between. The stricter of the two `controls` wins, the
shared `inventory_document`, `adapter` and `alerts` are kept, and a `LEDGER_PROMOTION` event records what was handed over.
Running it again changes nothing, and it works repeatedly: **sync, work, promote, sync, work, promote**. A draft that
was stored while it waited for data (`WAITING_DATA`) may be revised or finished in a later session without a repair and
still be handed over; any other replaced draft must have consumed one.

If the shared ledger holds events the session ledger lacks (Actions ran QA, a publisher wrote an intent) and the session
also has new work, the verdict is `DIVERGED`, nothing is written, and the reasons name the shared events. Work done on a
stale copy cannot be merged automatically: `sync` refuses too, because it would discard that work. Start every session with
`sync --apply`. `sync` fetches the documents the shared ledger depends on, including the source snapshots its articles
point to. A session ledger that holds state no event explains (a historical review recorded by older code, for instance) is
reported `INCONSISTENT` instead of being silently called "already included". A pull request that changes the ledger shows
this plan (`FAST_FORWARD`, `DIVERGED`, ...) in its `quality` run before anyone merges.

The schema-4 to schema-5 migration is deterministic and renames `VERIFIED` to `PUBLISHED` and `VERIFY_PENDING` to
`NEEDS_RECONCILIATION`; receipts are left byte-identical.

## Writers and automatic QA

Writers follow [the V5 writer brief](V5-WRITER-BRIEF.md). There is no reviewer step: a completed draft goes straight to
automatic QA, and the historical [reviewer brief](V5-REVIEWER-BRIEF.md) is kept only as history.

```
python3 -m thuha.cli --git-branch claim --session SESSION --agent-id claude-writer-W1
python3 -m thuha.cli --git-branch kit --topic-id TH-VI-0001 > kit.json     # same-language links, images with that language's alt text
python3 -m thuha.cli --git-branch precheck --topic-id TH-VI-0001 --file article.json     # exit 0 pass, 1 fix the article, 3 only data is missing
python3 -m thuha.cli --git-branch submit --slot W1 --session SESSION --fence FENCE --file article.json
python3 -m thuha.cli --remote qa --pending            # every completed draft, and READY drafts whose QA predates the policy or the text
```

An actual authorized AI session must do the research and writing; Actions never generate prose. Capture real
public source evidence with `source --url URL` (or `--external-fetch` from an authorized fetcher); if DNS, HTTP
or permissions fail, mark the source blocked — never invent a capture. Intake accepts at most 100 candidates and
checks the complete inventory and every queued intent.

**Article contract.** `topic_id`, `session`, `agent_id`, `source_commit`, `language` (`vi` for `TH-VI-####`, `en-US`
for `TH-EN-####` and legacy `TH-######`), `title`, `body_html`, `seo_title`, `meta_description`, `focus_keyword`,
`canonical`, `category_id`, `featured_media` (an existing image whose alt text is in the article's language; a Vietnamese alt text must contain at least one Vietnamese letter, because a short English caption cannot be told apart otherwise),
`sources`, `business_claims`. Submission saves the immutable document first, then its receipt; preserve the
SHA through quota exhaustion. Only changed bytes count as a repair (limit in policy). QA failure never makes an
Actions job rewrite prose. An empty `featured_media` is refused by `submit` unless the draft is stored with
`--waiting-for FEATURED_MEDIA`: QA cannot pass it, so it would only cost a repair.

**QA** is deterministic (raw automatic points out of 80, normalized to 100, threshold 85, any hard failure blocks) and
runs on the shared ledger for every completed draft. Historical review records neither gate it nor add points. Its outcomes:

| Outcome | What happened | Ledger | Exit code of `qa --pending` |
|---|---|---|---|
| `PASS` | every check passed | READY, report stored | 0 |
| `FAIL` | the article has a fault, or its score stays below 85 even with the data | NEEDS_REPAIR (a repair is spent when the writer resubmits changed text), or NEEDS_REVIEW after the repair limit | 0 (the failure is in the ledger) |
| `BLOCKED_DATA` | only pages the draft already links to are planned but not live yet, and with them it would pass as written | stays DRAFT_READY (a READY draft whose check can no longer be renewed goes back to DRAFT_READY); no repair spent; not a pass; recorded once, then checked again by every run at no ledger cost | 0 (3 when one topic is asked for) |
| `BLOCKED` / `INFRASTRUCTURE` | the inventory is stale, incomplete or public-only for Vietnamese, or the network failed | **nothing is evaluated, recorded or changed** | 2 (the run is red so a stale audit is noticed) |

A failure that *can* mean "the data does not exist yet" counts as a wait only when no edit could clear it: a link that points
nowhere, too few links while the site has live pages to link to, an image that exists but was not chosen, a chosen image the
inventory does not show, and a score that stays below the threshold are faults, never waits. The writer's `precheck` uses the
same classifier and adds only what a writer may declare with `--waiting-for` (below): an unfinished draft may wait for an image that
does not exist or for live content it will be completed with. Vietnamese QA needs an adapter or authenticated inventory.

## Drafts that wait for data

A finished text that lacks something no session can create (an image whose alt text is Vietnamese, live Vietnamese pages to link
to, an authoritative inventory) is stored instead of being held back or faked:

```
python3 -m thuha.cli --git-branch precheck --topic-id TH-VI-0004 --file article.json   # exit 3: only data is missing; data_waits / content_fails
python3 -m thuha.cli --git-branch submit --slot W1 --session S --fence F --file article.json --waiting-for FEATURED_MEDIA INTERNAL_LINKS AUTHORITATIVE_INVENTORY
python3 -m thuha.cli --remote recheck-data          # (protected job) clears only what the authenticated inventory really holds
python3 scripts/export_drafts.py                    # drafts/<language>/<ID>.json + drafts/INDEX.md, derived from the ledger
python3 -m thuha.cli --git-branch claim --session S --agent-id A --revise TH-VI-0004   # edit a stored draft whose data is still missing
```

`WAITING_DATA` is a stored state, never READY: `qa` refuses it, `qa --pending` skips it, the publisher cannot take it, it is not
claimable until `waiting_for` is empty, and the dashboard shows it in its own column with the missing codes. `FEATURED_MEDIA`
requires `featured_media` to stay empty. Finishing a draft after the data arrives is a completion, not a repair: it does not use
the three bounded repairs, and a lease lost half-way returns the topic to `WAITING_DATA`. A completed draft then goes through
automatic QA like any other. Each stored Vietnamese draft links only to category archives for now: once live Vietnamese content
exists, the writer adds one link to it when finishing (QA needs at least one live content link, and archives do not count). The owner-facts file can be captured as labelled first-party evidence (`source --repository-file
config/business-facts.json`); it is stale the moment that file changes, supports statements about the shop only and is never an
official source for a legal claim. A planning inventory (the committed authenticated snapshot) may feed claims, kits and admission for
seven days; QA and publication keep the six-hour limit.

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
A row becomes a topic only through `intake`, which needs captured dated sources and a recorded intent verdict (a
collision check of the topic against the inventory and the queue; this is topic admission, not an article review);
otherwise it stays `NEEDS_SOURCE`. After the ledger changes, run `scripts/export_queued.py` and
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

**A held draft** (`DRAFT_HELD`) is resolved by a person in WordPress: publish it and the next run records it; delete it
permanently and, once the grace period has passed, the next run closes the intent and the topic can publish again. A
trashed draft still carries the idempotency key, so it must be deleted permanently, not just trashed.

**What decides PUBLISHED.** WordPress returned an ID, status `publish`, the planned permalink in the right
language namespace, and the post carries this intent's owner, key and marker. Then (not before) the adapter
read-back is compared with the stored article and the result is kept in the receipt (`integrity`). A
`MISMATCH` opens an alert: no new post is published until `acknowledge`. The public page is checked afterwards;
failures back off (10 min, 30 min, 1 h, 3 h) and end as `FAILED_FINAL` after five attempts. They are shown on
the dashboard and never stop the queue. The first stage's two posts must have passed their public-page check
before the controlled-scale stage can start.

**Never.** No command updates or deletes existing WordPress posts or creates categories; no code POSTs twice
for one intent; nothing clears an intent by hand. All writes go through the companion plugin
([adapter guide](bilingual/ADAPTER.md)); until `adapter-preflight` succeeds the status is
`BLOCKED_ADAPTER_NOT_DEPLOYED`.

## Workflows

* `quality` — tests, matrices, plugin package, validation, dry-run; on `main` and on same-repository pull requests it
  also reads the real ledger and prints the promotion plan (read-only; a pull request shows `FAST_FORWARD` or the reason
  it cannot be handed over before anyone merges). Triggered by code, config, matrix **and ledger** changes.
* `thuha-ready-publisher` — after a successful quality run on `main`, hourly, or by hand. A manual run without `live` is the
  read-only preview: it runs `preflight` only and writes nothing (the `queue` job is skipped). Jobs: `preflight`
  (read-only, evaluates the release gate); `queue` (no WordPress secret: `promote --apply`, `audit --max-age 18000`,
  `qa --pending --language en`; each step carries on if the one before failed, and a refused hand-over fails the run at the
  end); `protected-publish` (only when the gate is open, inside `thuha-production`: adapter preflight, authenticated `audit`,
  `qa --pending`, `publisher --mode drain`; a failed audit or QA step does not stop the drain, which re-reads the inventory
  itself). `qa --pending` reports a failed or data-blocked draft in the ledger and exits 0; an unusable inventory exits 2 and changes nothing.
* `maintenance` — read-only health every six hours; manual tasks (`audit`, `coordinator`, `refill`, `intake`,
  `qa`, `recovery`, `promote`).
* `publisher` — manual single-topic modes (`dry-run`, `production`, `reconcile`, `verify`, `acknowledge`).

## Go-live (a separate owner decision)

The release lists `languages_enabled` (empty by default). Configure credentials inside the protected
`thuha-production` environment, not by copying another repository's secrets. Keep `main` review + the `quality`
check required; restrict the `factory-state` writer to the Actions app and forbid force pushes. Verify the
WordPress user and the registered Yoast REST fields. Coordinate any other tool publishing to the same site
(`cross_publisher_coordination_verified`). Approve a real pilot reference and the editorial policy
before enabling `config/release.json`. Unit tests do not prove these external controls exist.

Resource use: only read-only health and the hourly queue job run on a schedule; the expensive authenticated
audit runs in the protected job. A stale inventory blocks work and is shown in the dashboard. No scheduled AI
writer exists and production publishing is OFF.

The full public audit is committed. Authenticated SEO metadata is retained separately for the owner and
excluded from this public repository and history. Public focus-keyword values stay UNKNOWN.
