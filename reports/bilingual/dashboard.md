# ThuHa Writer bilingual dashboard

Generated: 2026-10-23T07:59:58.582722+00:00

- wordpress_published: 275
- site_live_verified_posts: 0
- factory_published_receipts: 0
- inventory_language_source: authenticated-snapshot
- production_enabled: False
- state_backend: local-offline-snapshot

## Languages (Vietnamese first)

| Language | Target | Live published | Unresolved intents | Remaining | Receipts |
|---|---|---|---|---|---|
| vi | 500 | 0 | 0 | 500 | 0 |
| en | 500 | 275 | 0 | 225 | 0 |

## Shared queue (not published posts)

| Language | Waiting for data | Awaiting review | Awaiting QA | QA pass | Publishing | Published | Needs repair | Held / unknown |
|---|---|---|---|---|---|---|---|---|
| vi | 17 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| en | 0 | 7 | 0 | 2 | 0 | 0 | 0 | 0 |

Public-page checks after publication: none yet. Public-page checks run after publication, back off and retry; they never stop the queue.

Session ledger hand-over: FAST_FORWARD (session v263, shared v5)

Adapter: NOT_VERIFIED (live status is PENDING until a credentialed preflight succeeds)

## Writer slots

| Slot | Lease state | AI execution |
|---|---|---|
| W1 | AVAILABLE | NOT_OBSERVED |
| W2 | AVAILABLE | NOT_OBSERVED |
| W3 | AVAILABLE | NOT_OBSERVED |
| W4 | AVAILABLE | NOT_OBSERVED |
| W5 | AVAILABLE | NOT_OBSERVED |
| W6 | AVAILABLE | NOT_OBSERVED |
| W7 | AVAILABLE | NOT_OBSERVED |
| W8 | AVAILABLE | NOT_OBSERVED |
| W9 | AVAILABLE | NOT_OBSERVED |

## Blockers

- Separate owner go-live approval outstanding
- No language enabled in the release (production stays OFF)
- BLOCKED_ADAPTER_NOT_DEPLOYED: no successful live adapter preflight is recorded
- Other publisher coordination not verified
- No external AI session lease; Actions do not generate prose
- The session ledger in this checkout is not in the shared ledger yet: the queue job (or `promote --apply`) hands it over
- 17 draft(s) wait for data (AUTHORITATIVE_INVENTORY x17, FEATURED_MEDIA x17, INTERNAL_LINKS x17): TH-VI-0004, TH-VI-0006, TH-VI-0011, TH-VI-0014, TH-VI-0016, TH-VI-0019, TH-VI-0033, TH-VI-0035, TH-VI-0043, TH-VI-0053, TH-VI-0058, TH-VI-0063
- 7 draft(s) wait for an independent review before QA: TH-000001, TH-000002, TH-000003, TH-000004, TH-000007, TH-000008, TH-000009

Existing articles are not attributed to ChatGPT or Claude without provenance. Live URL verification is not Google index verification.

## GitHub Actions

Status: UNKNOWN
