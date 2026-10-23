# ThuHa Writer V5 — writer-session runtime

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
  4 unchanged. Promotion back to `factory-state` is a trusted Actions step the
  owner runs after merge; until then, workflows reading `factory-state` do
  not see this session's drafts.
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
python3 -m thuha.cli $STATE claim --session SESSION --agent-id claude-writer-WN
python3 -m thuha.cli $STATE kit --topic-id TH-00000N > kit.json
# research: web_fetch each source, write a fetch record, then
python3 -m thuha.cli $STATE source --url URL --external-fetch record.json
python3 -m thuha.cli $STATE heartbeat --slot WN --session SESSION --fence FENCE
python3 -m thuha.cli $STATE precheck --topic-id TH-00000N --file article.json
python3 -m thuha.cli $STATE submit --slot WN --session SESSION --fence FENCE --file article.json
```

Rules the kit repeats and QA enforces: original English prose, two or more
`<h2>`, no body `<h1>`, no script/style/meta/iframe/form, internal links only
to live-verified URLs in the kit, featured media only from the kit's media with
alt text, reference prices only as declared `business_claims` with a disclaimer
sentence, an official `.gov.vn`/`.gov`/`.gov.uk` source whenever the text
mentions licences, permits, registration, law, visas or embassies, and never a
"no deposit", refund, delivery-policy or firsthand-testing claim.

`precheck` runs `quality.evaluate` on the draft with no state change, so a
writer fixes mechanical faults before `submit`; a changed resubmission still
counts toward the three bounded repairs.

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

## Independent review

A separate agent identity on the `trusted_reviewers` roster
(`claude-editorial-reviewer`) reads the exact submitted revision with `resume`,
verifies intent, factual accuracy against the captured sources, English,
originality, business facts and image relevance, and records a review for that
`article_sha` with `THUHA_REVIEWER_ID` set. The writer agent cannot review its
own draft. Then `qa --topic-id` recomputes everything; PASS moves the topic to
READY, FAIL to NEEDS_REPAIR. The roster is attribution metadata; the owner
confirms or replaces it at go-live.

## Admission of researched topics

`admit --file candidates.json --fetch-records records.json --reviewer-id ID
[--extra-queue other.json]` captures every declared source through its fetch
record, stamps the DISTINCT verdict with the current inventory digest and
admits the batch atomically through the existing `intake` contract. The extra
queue lets the researcher include another publisher's planned titles in the
collision check so two workflows targeting the same site do not cannibalize.

## Cycle report

`cycle` prints `LIVE TOTAL | FACTORY VERIFIED | PLANNED | WRITING | QA PASS |
QA FAIL | PUBLISHED | BLOCKED | REMAINING`. LIVE TOTAL comes from the latest
complete inventory document, never from a historical report; REMAINING is
2000 minus LIVE TOTAL. FACTORY VERIFIED and PUBLISHED count only readback
receipts.

## Known gaps

- Only 15 of the site's featured images carry alt text, so new drafts reuse
  existing verified images. Media upload is deliberately not implemented.
- An inventory older than six hours blocks claim, QA and admission. Re-dispatch
  the audit workflow; do not relax the age limit.
- The open PR #2 brief proposes a different site goal (500 EN + 500 VI). This
  V5 run follows the owner's 2,000 English-post instruction and records the
  conflict for the owner; it does not touch VI categories or that branch.
