# ThuHa Writer bilingual dashboard

Generated: 2026-10-23T05:42:43.986711+00:00

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

| Language | Awaiting review | Awaiting QA | QA pass | Publishing | Published | Needs repair | Held / unknown |
|---|---|---|---|---|---|---|---|
| vi | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| en | 6 | 0 | 2 | 0 | 0 | 0 | 0 |

Public-page checks after publication: none yet. Public-page checks run after publication, back off and retry; they never stop the queue.

Session ledger hand-over: FAST_FORWARD (session v137, shared v5)

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
- The session ledger in this checkout is not in the shared ledger yet: the queue job (or `promote --apply`) hands it over
- 6 draft(s) wait for an independent review before QA: TH-000001, TH-000003, TH-000004, TH-000007, TH-000008, TH-000009

Existing articles are not attributed to ChatGPT or Claude without provenance. Live URL verification is not Google index verification.

## GitHub Actions

Status: UNKNOWN
