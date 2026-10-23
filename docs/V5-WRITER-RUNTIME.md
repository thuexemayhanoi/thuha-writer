# ThuHa Writer V5 — writer-session runtime

> **Update 23 October 2026 (after the owner's decision).** The goal is **500 English + 500 Vietnamese posts, Vietnamese
> first**, not 2,000 English posts. This runtime is merged into the bilingual workflow: `kit`, `precheck`, `admit` and
> `cycle` are language-aware, topics carry a `language`, and a session ledger reaches the queue Actions read through
> `promote` (see [Operations](OPERATIONS.md)). Passages below that describe the observed execution boundary are kept as
> they were written; numbers measured for the old goal are marked.

V5 keeps every V4 gate and adds the pieces an authorized Claude session needs
to act as the W1–W9 AI runtime: labelled external source evidence, a read-only
writer kit, a non-mutating precheck that runs the production QA function, a
source-backed admission helper and the cycle report. GitHub Actions still only
orchestrates; production publishing is still OFF until the owner's separate
release. Nothing in V5 lowers the 85/100 threshold or any hard gate.

## Execution boundary observed on 23 October 2026

- The Claude cloud container is denied egress to `rentbikehanoi.com` and to
  research origins by the environment network policy. Only `api.github.com`
  is reachable. Therefore the live inventory is produced by the repository's
  own `ThuHa coordinator and maintenance` workflow (`task=audit`), dispatched
  from the session, and read back from `factory-state` as a content-addressed
  document. Research sources are fetched by an authorized external fetcher
  (the Parallel `web_fetch` tool) and recorded with `source --external-fetch`.
- The session's GitHub proxy allows REST reads but refuses every REST write
  ("Write access to this GitHub API path is not permitted through this
  proxy"), so the factory-state CAS adapter cannot be driven from here. The
  `GitBranchStore` (`--git-branch`) keeps the same `data/state/factory.json`
  and `data/documents/` paths but checkpoints through ordinary commits and
  pushes on the designated session branch, with explicit pathspecs and
  push-rejection CAS. The ledger was imported from `factory-state` at version
  4 unchanged. **Hand-over:** `thuha.cli --remote promote --apply` (run by the
  queue job after the branch is merged) moves this ledger into `factory-state`
  as a fast-forward: the live history must be the first part of the session
  history, documents are copied first, nothing is overwritten and a second run
  changes nothing. A new session starts with `--git-branch sync --apply` so its
  ledger begins from the shared one. Until the hand-over has run, workflows
  reading `factory-state` do not see this session's drafts.
- `GitHub` (REST adapter) falls back to the harness `GITHUB_TOKEN` when
  `THUHA_GITHUB_TOKEN` is absent and now sends `Content-Type: application/json`
  on writes. The destination-repository path guard and CAS semantics are
  unchanged.
- WordPress credentials, the protected environment, branch protection and the
  release approval are absent. The publisher stays BLOCKED; drafts that reach
  READY wait in the queue for the owner's go-live and the main merge.

## Writer loop (one Claude agent per slot)

```
export PYTHONPATH=src
STATE=--git-branch   # or --remote where factory-state REST writes are allowed
python3 -m thuha.cli --git-branch sync --apply          # once per session: start from the shared ledger
python3 -m thuha.cli $STATE next --language vi                 # read-only: what can be written now, in order
python3 -m thuha.cli $STATE claim --session SESSION --agent-id claude-writer-WN
python3 -m thuha.cli $STATE pack --topic-id TH-VI-0001 --out pack.json   # read-only: everything the repository holds for the topic
python3 -m thuha.cli $STATE kit --topic-id TH-VI-0001 > kit.json   # the older handoff; or TH-EN-0001 / legacy TH-00000N
# research: web_fetch each source, write a fetch record, then
python3 -m thuha.cli $STATE source --url URL --external-fetch record.json
python3 -m thuha.cli $STATE heartbeat --slot WN --session SESSION --fence FENCE
python3 -m thuha.cli $STATE build --topic-id TH-VI-0001 --body body.html --meta meta.json   # article.json from the pack + precheck
python3 -m thuha.cli $STATE precheck --topic-id TH-00000N --file article.json
python3 -m thuha.cli $STATE submit --slot WN --session SESSION --fence FENCE --file article.json [--waiting-for auto]
```

Rules the kit repeats and QA enforces (the kit prints the Vietnamese version for a Vietnamese topic: native
Vietnamese prose, same-language links and images, `giá tham khảo` for prices): original prose in the topic's language, two or more
`<h2>`, no body `<h1>`, no script/style/meta/iframe/form, internal links only
to live-verified URLs in the kit, featured media only from the kit's media with
alt text, reference prices only as declared `business_claims` with a disclaimer
sentence, an official `.gov.vn`/`.gov`/`.gov.uk` source whenever the text
mentions licences, permits, registration, law, visas or embassies, and never a
"no deposit", refund, delivery-policy or firsthand-testing claim.

`precheck` runs `quality.evaluate` on the draft with no state change, so a
writer fixes mechanical faults before `submit`; a changed resubmission still
counts toward the three bounded repairs. It also returns the advisory `lint`, a
`fixes` entry (where and how to fix) for every QA failure code and
`ready_to_submit`; `submit` re-runs it on the exact file and refuses a draft that is
known to fail before anything is stored (see [Operations](OPERATIONS.md#writers-and-automatic-qa)).

## External fetch record

```json
{"url": "https://example.gov.vn/page", "fetcher": "parallel-web-fetch", "status": "ok",
 "fetched_at": "2026-10-23T02:00:00+00:00", "title": "Page title", "content": "...text..."}
```

A record with an error, thin content, another URL, an unknown fetcher or a
timestamp older than a day is rejected. The resulting snapshot carries
`capture_method: external-fetcher` and the fetcher name, so an auditor can tell
it apart from a direct capture. A blocked source is recorded as blocked in the
topic notes; it is never invented.

## Automatic QA, no AI reviewer gate (owner instruction, 23 October)

Run `qa --topic-id` or `qa --pending` directly after a completed submission.
The latter also rechecks READY reports produced under another policy/revision.
The deterministic points available total 80, normalized to 100; >=85 is required
and any hard failure blocks regardless of score. `precheck` returns `would_pass_qa`,
the real score and `hard_fails`; it never assumes a reviewer will add points.
PASS moves the draft to READY; FAIL to bounded repair. WAITING_DATA and HELD are
excluded. NEEDS_REVIEW remains a legacy status for exhausted repair attempts,
not a mandatory reviewer step for otherwise passing drafts.

The publisher re-runs the same QA with fresh authenticated inventory before a
write. Legacy review documents and their events are retained without gating
or score credit. The optional `review` command is for historical attribution
only; never fabricate a reviewer to release the queue. Automated language and
source screens do not claim independent semantic or factual judgment.

## Admission of researched topics

`admit --file candidates.json --fetch-records records.json
[--reviewer-id ID] [--extra-queue other.json]` captures every declared source through its fetch
record and admits the batch atomically through the existing `intake` contract. No AI or human intent
reviewer is needed (owner update, 23 October): the automatic collision checks against the inventory and the
queue are the gate. A verdict a researcher supplies is stamped with the current inventory digest and, when it is not
DISTINCT, still blocks; `--reviewer-id` is optional attribution. The extra
queue lets the researcher include another publisher's planned titles in the
collision check so two workflows targeting the same site do not cannibalize.

## Cycle report

`cycle` prints `FACTORY PUBLISHED | PLANNED | WRITING | QA PASS | QA FAIL | PUBLISHED | BLOCKED | LIVE VI | REMAINING VI | LIVE EN | REMAINING EN`
plus a per-language block. Live totals come from the latest complete adapter (or authenticated) inventory plus the factory posts
WordPress confirmed since; with any other inventory they read `UNKNOWN`, never `0`. REMAINING is the language's 500 minus
live minus unresolved intents. FACTORY PUBLISHED and PUBLISHED count only receipts WordPress confirmed.

## Known gaps

- The media library is now listed in full by `audit`, but only 15 of the site's featured images carry alt text, all of it
  English, and no image has Vietnamese alt text. A Vietnamese article may only use an image whose alt text is Vietnamese, so
  none can pass QA until the owner adds such images. The kit reports `NEEDS_MEDIA` and the dashboard shows it. Media upload is
  deliberately not implemented. A writer does not stop for this: the draft is written and stored with
  `submit --waiting-for FEATURED_MEDIA ...` (see OPERATIONS.md, "Drafts that wait for data").
- An inventory older than six hours blocks QA and publishing. Claim, kit and admission accept the committed authenticated snapshot as a
  planning inventory for seven days; QA never does. Re-dispatch the audit workflow; do not relax the six-hour limit.
- The conflict with the open PR #2 brief (500 EN + 500 VI) is resolved: that is the goal.
