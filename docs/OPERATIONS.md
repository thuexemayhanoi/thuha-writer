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
python3 -m thuha.cli --git-branch sync --apply --discard-unpromoted > plan.json   # only after DIVERGED: replace the session ledger
python3 scripts/replay_unpromoted.py plan.json -- --git-branch        # then submit its drafts again (add --inventory FILE after -- when admission needs one)
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
stale copy cannot be merged automatically: `sync` refuses too, because it would discard that work, and it lists what the
session holds that the shared ledger lacks (`unpromoted`: one entry per draft with its article sha, session, agent and submission time,
the records of the topics only the session had admitted, plus the event counts). The way out is deliberate and never automatic:
`sync --apply --discard-unpromoted` replaces the session ledger with the shared one (refused while a writer holds a lease; the
replaced ledger stays in the branch history and no immutable document is deleted), and each listed draft is then submitted again.
`scripts/replay_unpromoted.py PLAN.json -- --git-branch` does that in submission order (`src/thuha/replay.py`): it admits again the
topics the shared ledger does not know, then one `claim` per draft (`--revise` for a draft that is `WAITING_DATA`, `--topic-id`
when it is `PLANNED`) with the session and agent the listing names, then `submit --file data/documents/<article_sha>.json
--waiting-for auto`. The same article document comes back with the same address and no repair is spent; the submit guard, the
data-wait classifier and automatic QA run as always. A draft whose topic has moved on in the shared ledger is skipped and reported,
the first refusal stops the run after releasing its lease, and `--override DIR` submits `DIR/<TOPIC_ID>.json` (a rewritten article)
instead of the stored document. This happened on 23 October 2026, when the owner merged PR #3 while a session was still writing
and the queue promoted the ledger and wrote QA: 22 Vietnamese drafts were submitted again that way (three English drafts on the list were finished with an image instead, because the refreshed inventory no longer allowed them to wait for one). It happened a second time the same
afternoon, once the queue was publishing and its publication events moved the shared ledger again: the round replaced the session ledger, submitted the English drafts again, rewrote the 35 waiting Vietnamese drafts to link to live pages and submitted the new batch. Start every session with `sync --apply`. `sync` fetches the documents the shared ledger depends on, including the source snapshots its articles
point to. A session ledger that holds state no event explains (a historical review recorded by older code, for instance) is
reported `INCONSISTENT` instead of being silently called "already included". A pull request that changes the ledger shows
this plan (`FAST_FORWARD`, `DIVERGED`, ...) in its `quality` run before anyone merges.

The schema-4 to schema-5 migration is deterministic and renames `VERIFIED` to `PUBLISHED` and `VERIFY_PENDING` to
`NEEDS_RECONCILIATION`; receipts are left byte-identical.

## Writers and automatic QA

Writers follow [the V5 writer brief](V5-WRITER-BRIEF.md). There is no reviewer step: a completed draft goes straight to
automatic QA, and the historical [reviewer brief](V5-REVIEWER-BRIEF.md) is kept only as history.

```
python3 -m thuha.cli --git-branch next --language vi      # what can be written now, in order (read-only; HELD topics are never offered)
python3 -m thuha.cli --git-branch claim --session SESSION --agent-id claude-writer-W1 [--topic-id TH-VI-0134]   # next in order, or this claimable topic (recorded as picked)
python3 -m thuha.cli --git-branch pack --topic-id TH-VI-0001 --out pack.json     # everything the repository already holds for the topic (read-only)
python3 -m thuha.cli --git-branch build --topic-id TH-VI-0001 --body body.html --meta meta.json   # article.json from the pack + the precheck, in one step
python3 -m thuha.cli --git-branch kit --topic-id TH-VI-0001 > kit.json     # the older read-only handoff: same-language links, images with that language's alt text
python3 -m thuha.cli --git-branch precheck --topic-id TH-VI-0001 --file article.json     # exit 0 pass, 1 fix the article, 3 only data is missing
python3 -m thuha.cli --git-branch submit --slot W1 --session SESSION --fence FENCE --file article.json [--waiting-for auto]
python3 -m thuha.cli --remote qa --pending            # every completed draft, and READY drafts whose QA predates the policy or the text
```

**Writing support (read-only, advisory).** Nobody types again what the repository already knows, and nobody learns a fault from a spent repair.

* `next` ranks what can be written now: Vietnamese first; topics that can be finished without waiting, then those that will be stored waiting
  (the expected `FEATURED_MEDIA` / `INTERNAL_LINKS`), then matrix rows that may be admitted (asking only for the shop's own facts or no
  source), then saved external sources that must be read again, and last the topics that overlap another (`CHECK_OVERLAP`). A HELD
  topic is never offered, and a topic that needs an official or manufacturer page nobody has read is counted, not offered. Topics about a
  policy the shop has not confirmed (deposit, refund, delivery, extension) are marked: the article says what to ask, never what the policy is.
* `claim` gives the next topic in order, Vietnamese first. A writer that knows from `next` which topics it can finish may name one with
  `--topic-id`: the topic must be claimable, unleased and in a language below its ceiling, and the claim event records `picked`. Without it a topic that
  needs a page nobody can read here would stand in front of all the ones that can be written.
* `next` also lists the stored drafts whose first-party evidence the shop facts file has outgrown (`stale_first_party_evidence`): such a draft cannot pass
  QA until the file is captured again and the draft is submitted with the fresh capture. See "When the shop facts change" below.
* `pack` assembles, for one topic, the confirmed intent and category chain, the canonical URL, the shop's name, address, hours, phone and
  reference prices (a price with no reference is listed as such), the saved sources that are still current and, separately, other topics'
  sources that fit, the live same-language pages and category archives it may link to (planned pages are listed but are not live links), the
  images whose alt text is in the article's language, the metadata and HTML bands, what the topic is expected to wait for, and a skeleton
  carrying the lease's session and agent. It writes nothing and invents nothing: what the repository does not hold is said to be missing.
* `build` composes the article from the pack's skeleton, a body file and a small meta file (`seo_title`, `meta_description`, optional
  `featured_media` that must be one of the pack's options, `business_claims`, `extra_sources`), saves it and runs `precheck`.
* `precheck` (and `build`) now also return `lint` (advisory findings; `fix` ones would be refused by `submit`, `consider` ones are judgement calls),
  `fixes` (where and how to fix every QA failure code, from `config/writing.json`), and `ready_to_submit` / `submit_problems` / `submit_waiting_for`.
  The lint never changes the score, a threshold or a hard failure. It reads Markdown left in the body, broken heading levels, padding by repetition,
  provenance leaking into the shop's voice, and likeness to the other stored drafts of the same language (contact lines are left out of that
  comparison, so a shared address is not "a template"). For prices it judges only a sentence that presents an amount as the shop's own (the shop
  is named, or the sentence speaks of a rental price per day, week or month): an amount the shop never gave, an amount tied to an unconfirmed
  policy, or a reference price that is not declared in `business_claims` or lacks the disclaimer. Fines and fees from official sources and the
  arithmetic of a worked example are never read as shop prices, and a sentence that says "ví dụ" / "for example" is treated as an illustration.
* `submit` runs the same precheck on the exact file first and refuses, **storing nothing and spending no repair**, a draft with a known fault
  (`NOT_SUBMITTED`, exit 1, with the fixes), a draft that depends on data that does not exist yet without saying so, and a declared wait for
  data that does exist (someone must choose that image or add that link). `--waiting-for auto` declares exactly what the check found missing
  (`FEATURED_MEDIA`, `INTERNAL_LINKS`); `AUTHORITATIVE_INVENTORY` is never a wait the writer has to declare. `--allow-faults` stores a faulty draft
  on purpose (it will come back from QA as a repair); the wait rules still apply to it.

On the shared ledger (`--remote`) `submit` evaluates a completed draft at once and dispatches the queue on a pass; an expired
inventory is first replaced by a fresh public read (GET only; if the site cannot be reached the old one is kept and QA refuses it,
recording nothing). Topic admission needs no reviewer: `admit` / `intake` check collisions automatically, a verdict a researcher
supplies only blocks when it is negative or was made on a stale inventory.

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

**QA** is deterministic (raw automatic points out of 80, normalized to 100, threshold 75 inclusive, any hard failure blocks) and
runs on the shared ledger for every completed draft. Historical review records neither gate it nor add points. Its outcomes:

| Outcome | What happened | Ledger | Exit code of `qa --pending` |
|---|---|---|---|
| `PASS` | every check passed | READY, report stored | 0 |
| `FAIL` | the article has a fault, or its score stays below 75 even with the data | NEEDS_REPAIR (a repair is spent when the writer resubmits changed text), or NEEDS_REVIEW after the repair limit | 0 (the failure is in the ledger) |
| `BLOCKED_DATA` | only pages the draft already links to are planned but not live yet, and with them it would pass as written | stays DRAFT_READY (a READY draft whose check can no longer be renewed goes back to DRAFT_READY); the writer's slot is freed; no repair spent; not a pass; recorded once, then checked again by every run at no ledger cost. If those pages never come, `claim --revise ID` lets a writer re-point the links (a completion, not a repair) | 0 (3 when one topic is asked for) |
| `BLOCKED` / `INFRASTRUCTURE` | the inventory is stale, incomplete or public-only for Vietnamese, or the network failed | **nothing is evaluated, recorded or changed** | 2 (the run is red so a stale audit is noticed) |

A failure that *can* mean "the data does not exist yet" counts as a wait only when no edit could clear it: a link that points
nowhere, too few links while the site has live pages to link to, an image that exists but was not chosen, a chosen image the
inventory does not show, and a score that stays below the threshold are faults, never waits. The writer's `precheck` uses the
same classifier and adds only what a writer may declare with `--waiting-for` (below): an unfinished draft may wait for an image that
does not exist or for live content it will be completed with. Vietnamese QA needs an adapter or authenticated inventory.

## When the shop facts change

`config/business-facts.json` is the owner's word about the shop. A first-party capture of it (`source --repository-file`) is current only while the file
still has the captured digest, so the moment the owner changes the file every earlier capture is stale and every draft that cites one fails QA with
`SOURCE_STALE_OR_UNVERIFIED`. Old documents, QA reports and receipts are never rewritten to hide this. What a session does, once per change:

1. `source --repository-file config/business-facts.json` captures the file again (a new immutable document).
2. `next` lists the affected stored drafts (`stale_first_party_evidence`). For each one that is not HELD: read what the change means for the text (a policy
   that used to be "ask the shop" may now have an answer), `claim --revise ID` (for a draft that waits) or claim it, `build` with the fresh capture in the meta
   file's `extra_sources` (`build` leaves the stale one out and says so) and `submit --waiting-for auto`. Finishing a waiting draft is a completion, not a repair.
3. A HELD draft is not resubmitted; if it is ever unheld it needs the same treatment first.

The 23 October 2026 confirmation of the extension fee (20,000 VND per hour; more than 6 hours is charged as one rental day) is the first such change:
the seven waiting Vietnamese drafts were re-captured and three of them (late return, day counting, switching to a weekly package) were rewritten around the confirmed fee.

## Drafts that wait for data

A finished text that lacks something no session can create (an image whose alt text is Vietnamese, live Vietnamese pages to link
to, an authoritative inventory) is stored instead of being held back or faked:

```
python3 -m thuha.cli --git-branch precheck --topic-id TH-VI-0004 --file article.json   # exit 3: only data is missing; data_waits / content_fails
python3 -m thuha.cli --git-branch submit --slot W1 --session S --fence F --file article.json --waiting-for auto    # or name the codes: FEATURED_MEDIA INTERNAL_LINKS
python3 -m thuha.cli --remote recheck-data          # (protected job) clears only what the authenticated inventory really holds
python3 scripts/export_drafts.py                    # drafts/<language>/<ID>.json + drafts/INDEX.md, derived from the ledger
python3 -m thuha.cli --git-branch claim --session S --agent-id A --revise TH-VI-0004   # edit a stored draft whose data is still missing (or one whose QA is BLOCKED_DATA)
```

`WAITING_DATA` is a stored state, never READY: `qa` refuses it, `qa --pending` skips it, the publisher cannot take it, it is not
claimable until `waiting_for` is empty, and the dashboard shows it in its own column with the missing codes. `FEATURED_MEDIA`
requires `featured_media` to stay empty. Finishing a draft after the data arrives is a completion, not a repair: it does not use
the three bounded repairs, and a lease lost half-way returns the topic to `WAITING_DATA`. A completed draft then goes through
automatic QA like any other. Eleven Vietnamese static pages are published (the adapter inventory of 23 October lists them; `data/bilingual/static-pages.json` records their
addresses and the evidence), so a Vietnamese draft links to the category archives of its topic and to the live page that fits it (prices, scooters, procedure, delivery and return, FAQ, contact):
QA needs at least one live content link, and archives do not count. The matrix row's service target (`internal_link_plan`, role `service`, status `LIVE_VERIFIED_ADAPTER_2026-10-23`)
names the page; four service keys (monthly, electric, old-quarter, sale) have no dedicated Vietnamese page (`NO_DEDICATED_LIVE_VI_PAGE`), so the writer picks the closest live page the pack lists. Every
draft then has a live link of its own and none depends on another draft being published first (a link to a sibling draft is only `planned`, so two drafts that link only to each other could never
pass). The 35 waiting Vietnamese drafts were rewritten that way on 23 October: the only thing they still wait for is an image whose alt text is Vietnamese.

**Links between waiting drafts must not form a loop.** QA fails a link to a page that is not live, so a draft can only pass after every draft it links to is published.
`next` therefore reports `planned_link_cycles` (groups of stored drafts that depend on each other, which can never pass) and `precheck`/`build` report `planned_links` and
`link_cycle` for the draft in hand, with the replacement text taken into account. Keep the links acyclic: a draft may link to a draft written before it, never back (the 2026-10-23
batches were pruned to such an order, and a mention of an unpublished sibling is plain text, not a link). Since the Vietnamese static pages are live, no draft needs a sibling draft to reach
its link minimum, and the drafts of 23 October were rewritten to link to live pages only; keep it that way. The owner-facts file can be captured as labelled first-party evidence (`source --repository-file
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
* `thuha-ready-publisher` — after a successful quality run on `main`, **when a writer's QA pass dispatches `thuha-qa-ready`**
  (`submit` and `qa` on the shared ledger do it; a session ledger in a branch and a draft stored with `--waiting-for` never do),
  hourly as the recovery fallback, or by hand. A manual run without `live` is the
  read-only preview: it runs `preflight` only and writes nothing (the `queue` job is skipped). Jobs: `preflight`
  (read-only, evaluates the release gate); `queue` (no WordPress secret: `promote --apply`, `audit --max-age 18000`,
  `qa --pending --language en`; each step carries on if the one before failed, and a refused hand-over fails the run at the
  end); `protected-publish` (only when the gate is open, using repository Actions Secrets: adapter preflight, authenticated `audit`,
  `qa --pending`, `publisher --mode drain`; a failed audit or QA step does not stop the drain, which re-reads the inventory
  itself). `qa --pending` reports a failed or data-blocked draft in the ledger and exits 0; an unusable inventory exits 2 and changes nothing.
* `maintenance` — read-only health every six hours; manual tasks (`audit`, `coordinator`, `refill`, `intake`,
  `qa`, `recovery`, `promote`).
* `publisher` — manual single-topic modes (`dry-run`, `production`, `reconcile`, `verify`, `acknowledge`).

## Go-live (a separate owner decision)

The release lists `languages_enabled` (empty by default). Configure `THUHA_WP_USER` and `THUHA_WP_APPLICATION_PASSWORD` as repository Actions Secrets. No GitHub Environment or `THUHA_GO_LIVE_APPROVAL` variable is required; never copy secrets between projects. Keep `main` review + the `quality`
check required; restrict the `factory-state` writer to the Actions app and forbid force pushes. Verify the
WordPress user and the registered Yoast REST fields. Coordinate any other tool publishing to the same site
(`cross_publisher_coordination_verified`). Approve a real pilot reference and the editorial policy
before enabling `config/release.json`. Unit tests do not prove these external controls exist.

Resource use: only read-only health and the hourly queue job run on a schedule; the expensive authenticated
audit runs in the protected job. A stale inventory blocks work and is shown in the dashboard. No scheduled AI
writer exists; the owner enabled release separately on 23/10/2026. Real publishing is confirmed only by WordPress readback and durable receipts.

The full public audit is committed. Authenticated SEO metadata is retained separately for the owner and
excluded from this public repository and history. Public focus-keyword values stay UNKNOWN.
