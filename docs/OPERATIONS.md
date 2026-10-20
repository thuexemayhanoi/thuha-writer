# Operating ThuHa Writer V4

All commands run from this repository with `PYTHONPATH=src`. There is no pip
install step. Use Python 3.11+ on Linux. No model API credentials are needed.

## Authoritative state

Use `--remote` for every cross-session operation. The destination-only GitHub
token is read from `THUHA_GITHUB_TOKEN`; never put it in a command argument or
candidate file. The state adapter initializes factory-state from main if absent
and writes only `data/state/factory.json` and content-addressed JSON documents.
The branch is operational data, never executable code. main remains the source
of code and policy. Local `.runtime/` is for tests/offline development only.

```
python3 -m thuha.cli --remote --output artifacts/live-audit audit
python3 -m thuha.cli --remote refill
python3 -m thuha.cli --remote coordinator
python3 -m thuha.cli --remote claim --session chatgpt-20261021-a --agent-id chatgpt-work
```

An actual authorized AI session must read the returned topic and draft, do its
research/writing and keep its heartbeat alive. Capture real public source
evidence with `source --url URL`; keep the returned document address and explain
the supported claims. If DNS, HTTP or permissions fail, mark the source blocked;
never invent a capture. Intake accepts at most 100 candidates and checks the
complete inventory and every queued intent before it admits PLANNED records.

## Article contract

Submit a JSON object with topic_id, session, agent_id, source_commit, language
`en-US`, title, body_html, seo_title, meta_description, focus_keyword, canonical,
category_id, featured_media (an existing verified image), sources and declared
business_claims. See the synthetic fixture in tests for field shape; test data
is not a publishable article or real research evidence.

```
python3 -m thuha.cli --remote heartbeat --slot W1 --session SESSION --fence FENCE
python3 -m thuha.cli --remote submit --slot W1 --session SESSION --fence FENCE --file article.json
python3 -m thuha.cli --remote qa --topic-id TH-000001
```

Submission first saves the immutable document, then its receipt. Preserve the
returned SHA through quota exhaustion. Reopen it from the remote store to resume.
Only changed bytes count as a repair, up to the policy limit. At the limit, the
latest held document remains addressed in state and needs review. QA failure
does not make an Actions job rewrite prose; the external writer repairs it and
resubmits. Expired leases never permit overwriting another live writer's work.

An independent authorized reviewer must attest the exact revision's intent,
factual accuracy, English, originality, business facts and image relevance. The
reviewer allowlist starts empty. Reviewer metadata is not cryptographic proof;
protect code/policy and the state writer before trusting it for production.

## Publisher and emergency stop

```
python3 -m thuha.cli --remote publisher --mode dry-run
python3 -m thuha.cli --remote controls --pause on
python3 -m thuha.cli --remote controls --emergency-stop on
python3 -m thuha.cli --remote publisher --mode reconcile --topic-id TH-000001
python3 -m thuha.cli --remote --output artifacts report
```

No command updates/deletes existing WordPress posts or creates categories. A
timeout, 4xx/5xx or checkpoint error after reservation remains an intent to
reconcile. Do not clear intents or POST again. Reconciliation requires exact
ownership marker, content, ID/status/URL, category, image and SEO readback.
Unknown outcomes consume the two-post pilot budget until reviewed.

Go-live is a separate owner decision. Configure new repo-specific credentials
inside the protected thuha-production environment, not by copying another
repo's secrets. Keep main required review + the `quality` check; restrict the
factory-state writer to trusted automation and forbid force pushes. Verify the
WordPress user and registered Yoast REST fields. Coordinate any other factory
publishing to the same site. Approve a real pilot reference, reviewer roster
and editorial policy before enabling config/release.json. Unit tests do not
prove these external controls exist.

## Workflows and resource use

Three workflows cover the requested responsibilities without ten overlapping
schedulers: quality (unit/integration/regression + dry-run), maintenance
(coordinator, research intake/refill, QA/repair queue, recovery, audit/report),
and the guarded publisher/post-publish verifier. Only read-only health runs
every six hours; expensive audits and state-changing operations are explicit
dispatches while go-live is pending. A stale inventory blocks work and is shown
in the dashboard. No scheduled AI writer or production publishing is enabled.

The full public audit is committed. Authenticated SEO metadata is retained
separately for the owner and excluded from this public repository and history.
Public focus-keyword values stay UNKNOWN rather than disclosing private fields.
