# Direct Writer → QA 75 → WordPress Publisher

> Filename retains `QA85` for backwards links; **current effective threshold is 75 inclusive**. Score below 75 or any hard failure fails, in both VI and EN.

This is the **simple, event-driven** editorial path for `thuexemayhanoi/thuha-writer`.

```text
Authorized Claude/ChatGPT writer(s), W1/W2/W3 (or other available slots)
  → --remote submit (durable content hash + lease/provenance)
  → deterministic automated QA ≥75, fail closed on all hard errors
  → status READY + GitHub repository_dispatch: thuha-qa-ready
  → preflight + protected publisher immediately (no cron wait)
  → live WordPress duplicate/category/source/QA checks
  → one POST + durable intent + WordPress readback + verified receipt
```

- Topic intake also runs **without a separate intent reviewer**: primary-source capture, exact live taxonomy, URL/slug/intent/title collision checks and declared negative verdict protection stay mandatory.
- If the 6-hour WordPress inventory expires, a write-capable CLI operation automatically fetches a new **read-only live WordPress inventory** and stores its snapshot before QA/claim/intake. No scheduled audit or guessed inventory bypass is needed. Read-only preflight remains read-only.
- **No AI or human article-review gate.** `config/qa.json` keeps **score_threshold=75**, all existing technical/content/source/taxonomy/duplicate and safety hard failures. The raw automatic points (80 at most) are normalized to 100 and a review adds none, never a fake review. The score is exactly that normalization: an extra H2-structure bonus, proposed in the first version of this runbook, is not part of it, so the threshold of 75 keeps one meaning.
- **No timed publication waiting.** `minimum_post_interval_seconds=0`, but queue serialization, release stage, daily capacity and WordPress/REST limits remain. The hourly cron is a recovery fallback, **not** the primary trigger.
- Each writer must be a **real authorized external AI session**. GitHub Actions never invents prose, fake heartbeats, references, publications or QA.
- `--remote submit` calls QA automatically for a completed draft and emits a repository dispatch for each passing revision; a draft stored with `--waiting-for` is not evaluated and dispatches nothing, a session ledger in a branch never dispatches (Actions do not read it), and an unusable inventory leaves the stored draft for the scheduled QA instead of failing the submit. `--remote qa` is supported for recovery/batch QA and dispatches passing revisions. If dispatch delivery fails, the article stays READY and the cron fallback can still drain it.
- Publisher repeats full QA on the live WordPress inventory and validates immutable receipts; uncertain POST outcomes are held for reconciliation, never blindly retried.
- `main` contains code/config and the isolated `factory-state` branch contains mutable editorial state. Never edit state by hand.
- Per-article automated checks **cannot establish true factual accuracy or search rankings**. Writers must use real verifiable sources; hard-fails prevent known unsafe/duplicate/unsourced content.

## Go-live without a review queue

This QA75 change does not modify `config/release.json`. **A separate owner-approved update on 23/10/2026 enabled `auto-scale` with a 50-post daily cap.** The real WordPress adapter, taxonomy, fresh inventory and publication receipts must still be verified before claiming live success. The original **two-post pilot** was the historical safety ramp before scaling; it must **not** be configured again as a new required manual approval. The current ledger had **9 EN PUBLISHED receipts** at version 448 (23/10/2026). WordPress credentials belong in repository-level GitHub Actions Secrets `THUHA_WP_USER` and `THUHA_WP_APPLICATION_PASSWORD`. The separate GitHub Environment and `THUHA_GO_LIVE_APPROVAL` variable are not used; owner authorization stays in `config/release.json`. Do not copy credentials from unrelated repositories.

**For new sessions:** Do not ask the owner to reauthorize the already enabled release or rerun the original pilot. Instead read `config/release.json`, run appropriate offline tests/validation on code changes, inspect the latest real authenticated WordPress audit, cross-publisher collision checks and immutable readback receipts, then let the existing publisher drain eligible QA75 articles within current caps. Do not reset publication IDs or relax hard gates. If access or verified media/links are missing, preserve the waiting state and report the specific blocker.

## Writer CLI

```bash
export PYTHONPATH=src
python3 -m thuha.cli --remote brief --limit 3
python3 -m thuha.cli --remote claim --session YOUR_SESSION --agent-id YOUR_AGENT --slot auto
# Write a real, source-backed JSON draft with topic_id, session, agent_id, etc.
python3 -m thuha.cli --remote submit --slot W1 --session YOUR_SESSION --fence ACTUAL_FENCE --file article.json
# If QA PASS, publisher dispatch is immediate; if FAIL, repair and resubmit.
python3 -m thuha.cli --remote report
```

Do not paste application passwords into commands or commit secret-bearing files. The builder must preserve existing URLs, canonicals and WordPress taxonomy.
