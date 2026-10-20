# ThuHa Writer — Incremental Execution Roadmap

Every phase produces a verifiable checkpoint. Do not enter the next phase on the strength of an AI-generated narrative alone.

## Phase 1 — Audit & safe baseline (CURRENT)

**Deliverables:** English project README, read-only production configuration and a reference/live-WordPress audit with sample article-level evidence.

**Exit criteria:** Correct target domain, reference repository separated from destination, no workflows activated, no WordPress writes, and an explicit list of known and unknown facts.

## Phase 2 — Complete read-only WordPress inventory

Build a Python standard-library auditing CLI and tests. Its only network operations are GET against the authorized WordPress REST API; no credentials are required for public data. Preserve audit timestamps, HTTP status, pagination, and partial-failure markers. Never output secrets.

Inspect ALL accessible published posts and pages, not just the first WordPress REST API page. Collect stable WordPress IDs, permalinks, slugs, title, description, canonical, publish status, primary category and exact parent chain, featured media ID, internal in-body anchors, word count and hints of intent overlap. Internal HTML, metadata and page head may require separate checks. Mark missing access as UNKNOWN, not PASS.

**Exit criteria:** manifest and evidence-backed counts, reproducible samples, no inconsistent pagination, and fresh baseline that is safe to use for deduplication.

## Phase 3 — Research and topic admission (no publishing)

Read actual WordPress taxonomy and reconcile already published content. One canonical search intent per target URL. Require clear titles, questions answered, cluster, primary keyword, category ID and supporting references. Research cannot fabricate pages, legal rules, current opening times, booking policies or NAP.

**Exit criteria:** reviewable and deduplicated PLANNED records; category mismatches and overlaps on hold.

## Phase 4 — W1–W9 coordination and draft review

Implement durable atomic leases, specific session identity, heartbeat and expiry. An expired session never implies a model is still active. Each AI agent must run through an actual user-authorized session and submit a unique revision with a hash and provenance. GitHub runners never pretend to write articles without a model.

**Exit criteria:** unit tests for concurrent claims, stale leases, resuming after quota exhaustion, unchanged content and provenance.

## Phase 5 — Quality gates

Evaluate useful English writing, intent, firsthand-claim accuracy, verified source evidence, canonical and taxonomy matches, source freshness, internal links, FAQ where helpful, basic accessibility, Yoast-ready metadata and content overlap. Score thresholds need explicit owner approval; hard-fail conditions cannot be overridden by a numerical score.

**Exit criteria:** sample articles PASS/REVIEW/FAIL deterministically and independently under tests.

## Phase 6 — Controlled publishing pilot

Only after the owner explicitly approves, configure GitHub secrets in a restricted environment; check branch protection and least privilege. Publish in a very small bounded batch. A POST is preceded by durable intent and duplicate checks; a timeout produces NEEDS_RECONCILIATION, never a blind retry. Verify WordPress ID, exact URL, status, category, title, canonical, and metadata in live readback, then append an immutable verified receipt.

**Exit criteria:** owner-approved pilot has zero duplicate posts and demonstrable rollback/stop behavior. Do not assume a reverted Git commit deletes a WordPress post.

## Phase 7 — Scale with feedback

Expand gradually with monitoring, separate content-creation and SEO-optimization jobs, image QA, link coverage and independent delivery receipts. Stop on elevated errors, unexpected category drift, duplicate risk, exhausted AI quota or missing publication credentials.

**Target:** 2,000 live-verified English WordPress articles with reliable attribution, without compromising existing SEO.

## Project boundaries

- Modify ONLY `thuexemayhanoi/thuha-writer` while developing this system.
- Reference `thuexemayhanoi/wp-writer` is READ ONLY.
- Production WordPress `https://rentbikehanoi.com` is READ ONLY until explicit future approval for a specific write phase.
- Theme repositories, site appearance, SEO settings and existing published URLs are out of scope.
- Do not create paid-AI API dependencies without explicit approval.
