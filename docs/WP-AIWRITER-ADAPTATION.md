# ThuHa Writer: safely adopted WP AIWriter execution pattern

Source (read-only architectural reference): https://github.com/thuexemayhanoi/wp-aiwriter

Destination (only editable repository): https://github.com/thuexemayhanoi/thuha-writer

Production WordPress (English en-US ONLY): https://rentbikehanoi.com

## Reusable workflow (without copying the source site's data)

- An external ChatGPT/Claude agent uses `PYTHONPATH=src python3 -m thuha.cli --remote brief --limit 10` to discover planned, unclaimed English tasks; brief is not a generator and never publishes.
- W1–W9 use existing remote CAS/leases to claim, research, write, submit, repair, receive independent editorial review and pass single-policy QA (threshold 85, all hard gates).
- `ThuHa V4 quality` still tests source code and safely previews publication without a WordPress POST.
- A *new* `ThuHa QA to guarded queue publisher` workflow listens only for successful **push-triggered quality on main**, offers safe manual preview and checks once hourly for QA-ready, approved work. Production job is skipped when release is OFF.
- On a separately approved go-live the protected `thuha-production` environment runs a guarded queue drain. It uses the existing published-readback mechanism, durable write-ahead intent, global lease, live duplicate checks, no overwrite, unchanged category IDs and receipts.
- The queue drain respects `config/release.json` (two-item pilot first, independently approved later controlled scale, maximum daily count, min interval). Unknown POST outcome halts subsequent publishing until reconciliation. This is deliberately **not** a quota bypass.

## Do NOT import from WP AIWriter

Source `wp-aiwriter` is for **blog.rentbikehanoi.com** and its VI/EN Core routes and /en/ publishing. No source `en/posts`, WordPress IDs, topic registry, state ledgers, secrets, service policies, category IDs, canonical routes, /en/ plugin dependencies, branch state, or previously approved source-site go-live flags transfer to `thuha-writer`.

WordPress data and exact taxonomy must be freshly validated against rentbikehanoi.com before each POST. All posts authored and published by other writer workflows remain protected; cross-publisher collision prevention must be verified first.

## Go-live is not implied by this code migration

The current `config/release.json` is disabled, unapproved and paused. The `config/qa.json` reviewer allowlist is empty. No production WordPress posts are published by applying this workflow.

Before production: verify enforced GitHub branch review and status checks, restrict factory-state writes, set `thuha-production` environment reviewers and repo-specific WordPress secrets, choose an actual independent reviewer and run two separately approved, independently verified pilot posts. Then separately approve controlled scale. Until then, the workflow provides safe dry-run preflight only.

New QA checks are in `tests/test_pipeline.py`; existing V4 tests are retained. Never attribute external AI-writing to GitHub Actions; it only orchestrates.
