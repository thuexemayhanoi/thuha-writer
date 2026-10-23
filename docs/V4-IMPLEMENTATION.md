> **HISTORICAL V4 IMPLEMENTATION RECORD (superseded, 23/10/2026).** References below to QA85, mandatory independent reviewers, protected GitHub Environments or release OFF are historical design assumptions, **not** current instructions. Current writer policy: QA >=75 inclusive, zero hard failures, release enabled auto-scale 50/day. Refer to [AGENTS.md](../AGENTS.md), current `config/qa.json`/`config/release.json` and the latest shared ledger. No article, source or receipt is changed by this note.

# ThuHa Writer V4 — implementation and operating boundaries

This is independently implemented Python standard-library code. The reference
repository was inspected at the commit recorded in
`reference-architecture-inventory.json`; no operational state, policies,
credentials, content or implementation code was imported.

## Implemented paths

- `audit.py`: all-page WordPress pagination, public URL/head checks, taxonomy
  ancestry, media/alt lookup, headings, body-link graph, content fingerprints,
  protected URLs and conservative SEO review matrix.
- `store.py`: local atomic files/flock for offline development; authoritative
  GitHub CAS on **factory-state**, with separate content-addressed documents.
  Never use local state to coordinate multiple computers or production.
- `coordinator.py`: W1–W9, one topic per lease, fencing ID, heartbeat,
  expiration, release and durable draft revisions. Availability is not proof
  that an AI process exists.
- `research.py`: source-capture receipts, inventory-bound intent review,
  existing category path validation, collision checks, atomic intake and
  bounded low-stock research requests. Requests are not PLANNED topics.
- `quality.py`: one policy in `config/qa.json`, independently recomputed
  technical gates, immutable report documents, bounded repair queue and a
  separate semantic/factual/English/image review requirement.
- `publisher.py`: default OFF, explicit single-topic pilot, independent live
  inventory, trusted QA recomputation, protected release/security checks,
  global lease, remotely durable intent before the only POST, exact
  readback, immutable receipts and reconciliation without another POST.
- `dashboard.py`: site totals separate from factory receipts and declared
  external-session agent IDs; uncertain outcomes, leases and blockers.

## Real execution boundary

GitHub Actions can run these programs. It cannot manufacture a free model
runtime or keep a closed ChatGPT/Claude session writing. An authorized external
AI session must perform research, write/revise articles and submit revisions.
No model API or paid AI dependency is present.

The technical QA score is not factual proof. `trusted_reviewers` starts empty;
unreviewed prose cannot reach READY. Human/AI reviewer IDs are attribution
metadata, not cryptographic identities. Enforced repository access controls
are required before they can be trusted for production. Writers must not
change policies, source, workflows, QA reports or receipts.

The production pilot additionally requires a separate owner approval record,
protected environment approval reference, publish-capable WordPress credentials,
registered Yoast REST metadata, enforced main review/status checks, a restricted
factory-state automation writer and coordination with any other publisher
targeting the same website. None is assumed from a green unit test.

## Single source for QA

`config/qa.json` uses 85 as a conservative development default. Confirm the
editorial threshold and trusted reviewers during the separate go-live review.
Neither a lower threshold nor high scores bypass hard failures. Archived Phase
1 descriptions remain historical; current configuration points to this file.

## Source and state separation

Code/configuration is on main. Runtime documents, leases, topic registry and
publication receipts belong on factory-state. This avoids requiring the
automation writer to bypass main's code-review protection. Workflows always
execute trusted main code and never execute code from a research/writer branch.
State path restrictions and CODEOWNERS are defense in depth, not substitutes
for enforced GitHub permissions. Remote CAS is fail-closed on conflicts.

## Audit limitations

The public inventory records public evidence. An authenticated focus-keyword
supplement is kept separately for the owner, outside public Git history.
Neither report claims Google indexing, traffic performance, exhaustive
legal/factual validation or human-level English/semantic review. A body-link
orphan is a graph hint; menu/footer links are excluded. Unknown internal targets
can be category/media pages and are not labeled broken without a fetch.

The initial implementation does not rewrite old WordPress posts, create
categories, upload media, alter SEO settings, modify the theme, or enable
production publishing. Infrastructure failures remain separate from content
repairs. Invalid state is held for review, not silently reset.

## Bilingual deltas (current behavior; the text above predates them)

- `language.py`: language registry, URL namespaces (`/vi/…`), slug rules, diacritic and
  function-word screens. `quota.py`: per-language ceilings (500 each), unknown outcomes counted.
- `store.py`: state schema 5 with an append-only, idempotent migration from schema 4 (every
  pre-existing topic, request, lease and intent was English; receipts are untouched). Topic
  language, ID prefix and URL namespace must agree; one WordPress slug per topic across languages.
- `coordinator.py` / `research.py` / `pipeline.py`: Vietnamese-first claim, refill and drain;
  repairs first within a language; a language at its ceiling takes no writers; admission capacity
  is ceiling − live posts − open topics, per language.
- `quality.py`: language label, category-chain language, body/title/meta/alt screens, same-language
  live-verified internal links (cross-language body links fail), Vietnamese regulated/first-hand/
  price-disclaimer rules, per-language length floor, review must name the language and attest
  `native_language` and `no_machine_translation`.
- `adapter.py` + `wordpress/thuha-native-vi-publisher`: the only write path (create-only,
  idempotent, marker before publish) and the complete two-language inventory. `http.py` refuses any
  other POST. `publisher.py` verifies the adapter readback and the public page (canonical, title,
  meta, `<html lang>`, no foreign hreflang, schema).
- `matrix.py`: seeds → validated matrices; `package.py`: reproducible ZIP and static safety scan.


## Deltas of 23 October 2026 (shared queue, publication semantics)

* `ledger.py`: `plan`, `promote`, `sync` — fast-forward-only hand-over of a session ledger into `factory-state`; `store.migrate` is
  deterministic so independently migrated chains compare; stores gained `raw()` and `adopt()`.
* `publisher.py`: PUBLISHED on WordPress's own ID/status/permalink; adapter read-back recorded as `integrity` with an alert; public-page
  crawl is `post_check` (back-off, five attempts, never blocking); phases `DRAFT_HELD`, `NOT_SENT`, `REJECTED`; `PublishBlocked`;
  `reconcile`/`reconcile_all`; grace period for an intent WordPress never saw.
* `pipeline.drain`: reconcile, publish Vietnamese first, send an unpublishable topic back to repair and carry on, run due checks, report the stop.
* `quality.pending_qa`, `audit --max-age`, full media library in the inventory, `quota.effective`.
* Workflows: queue job without WordPress secrets; protected job; `quality` also triggers on ledger paths.
