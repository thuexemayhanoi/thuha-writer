# ThuHa Writer bilingual dashboard

Generated: 2026-10-23T14:01:38.935781+00:00

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

| Language | Waiting for data | Awaiting QA | QA waits for data | QA pass | Publishing | Published | Needs repair | Held / unknown |
|---|---|---|---|---|---|---|---|---|
| vi | 35 | 0 | 0 | 0 | 0 | 0 | 0 | 11 |
| en | 0 | 0 | 0 | 19 | 0 | 0 | 0 | 0 |

Public-page checks after publication: none yet. Public-page checks run after publication, back off and retry; they never stop the queue.

Session ledger hand-over: FAST_FORWARD (session v557, shared v5)

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
- 35 draft(s) wait for data (FEATURED_MEDIA x35, INTERNAL_LINKS x35): TH-VI-0003, TH-VI-0004, TH-VI-0008, TH-VI-0011, TH-VI-0013, TH-VI-0016, TH-VI-0018, TH-VI-0019, TH-VI-0022, TH-VI-0026, TH-VI-0033, TH-VI-0058

Existing articles are not attributed to ChatGPT or Claude without provenance. Live URL verification is not Google index verification.

## GitHub Actions

Status: UNKNOWN
