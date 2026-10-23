# ThuHa Writer V4 delivery checkpoint — 21 October 2026

> **HISTORICAL — English-only, 2,000-post era.** Superseded by the bilingual 500 + 500 goal; kept as the record of the 21 October 2026 checkpoint. See `docs/bilingual/IMPLEMENTATION-STATUS.md` for current status.

## Verified implementation

Independently written stdlib modules cover complete read-only inventory,
taxonomy and protected URLs, W1–W9 fenced leases, remote CAS on factory-state,
atomic content-addressed checkpoints, source-backed intake and refill requests,
single-policy technical QA, independent editorial review gates, bounded repair,
default-OFF publisher, durable intents, safe reconciliation, post-publication
readback and receipts, pause/emergency controls and reporting.

Three pinned, least-privilege workflows cover CI, maintenance/controller tasks
and the protected publisher pilot. The first real GitHub quality run succeeded:
https://github.com/thuexemayhanoi/thuha-writer/actions/runs/39479456140
It ran unit/integration/regression tests, Python and YAML validation, a publisher
dry-run and artifact reporting. The expanded local suite has 61 passing tests.
No test sends a WordPress POST. Publisher production remains disabled.

The factory-state seed at `34d368528b25faaefbfa750cedf326a1bd31a9f7` contains
two PLANNED English museum/public-art topics. Both have actual HTTP 200 source
captures from the official museum or Vietnam Tourism site, plus a comparison
against the complete live post inventory and exact existing category ancestry.
There are no draft articles, claimed writer slots or publication receipts.
Refill requests remain capped at 100; source-backed admission is mandatory.

## WordPress audit evidence

The complete technical snapshot covers 273 published posts, 6 pages and 10
categories. Every captured public URL returned HTTP 200 and its own canonical.
All post SEO titles and descriptions were populated; rendered title/meta values
matched REST Yoast values. Every page exposed a schema block. The first snapshot
recorded presence and REST graph types; the newer collector also validates
JSON-LD syntax on future audits. This is not Google index-status evidence.

Public findings: 112 posts lack a featured image; 7 lack body internal links;
76 graph entries have no inbound body links and need context review (menus and
footer are not part of that graph). Seven links point outside the captured
post/page set; they resolve to three category/archive URLs, not proven broken
links. No existing post, category, SEO setting, URL or theme was edited.

Authenticated Yoast focus-keyword evidence was collected separately for the
owner. It is intentionally absent from this public repository and its public
commit ancestry. Public inventory fields remain UNKNOWN where public REST does
not expose them. The first attempted push was stopped before disclosure; the
successful commit was built directly on the original repository head with the
authenticated export excluded. No rejected payload was pushed indirectly.

## Remaining gates — do not describe the factory as live

- Obtain a separate, specific go-live approval for the two-post pilot.
- Set and verify new repo-specific WordPress credentials in thuha-production;
  no credentials or secrets were copied from the reference repository.
- Enforce main review + quality status, restrict factory-state writes to trusted
  automation, and configure environment reviewers. These controls are not
  established by CODEOWNERS or passing tests.
- Approve real independent reviewer identities and the editorial threshold.
  Semantic/factual review cannot be fabricated by a deterministic score.
- Coordinate other publishers targeting the same production website.
- Attach a real authorized external ChatGPT/Claude session for writing and
  repair. An AVAILABLE slot is not an AI runtime.
- Complete deep factual, English and semantic/cannibalization review of legacy
  content. The inventory and fingerprint matrix identify work, not semantic
  certainty. No bulk fixes have been made to old articles.

After two verified pilot receipts, controlled scale still requires a separate
expansion release, daily/total limits, fresh live duplicate checks and the same
quality gates. The publisher stops when the website reaches 2,000 published
posts; it does not generate duplicates to inflate a counter.
