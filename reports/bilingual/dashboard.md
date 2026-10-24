# ThuHa Writer bilingual dashboard

Generated: 2026-10-24T08:52:41.474645+00:00

- wordpress_published: 275
- site_live_verified_posts: 0
- factory_published_receipts: 30
- inventory_language_source: authenticated-snapshot
- production_enabled: True
- state_backend: local-offline-snapshot

## Languages (Vietnamese first)

| Language | Target | Live published | Unresolved intents | Remaining | Receipts |
|---|---|---|---|---|---|
| vi | 500 | 21 | 0 | 479 | 21 |
| en | 500 | 284 | 0 | 216 | 9 |

## Shared queue (not published posts)

| Language | Waiting for data | Awaiting QA | QA waits for data | QA pass | Publishing | Published | Needs repair | Held / unknown |
|---|---|---|---|---|---|---|---|---|
| vi | 0 | 0 | 0 | 46 | 0 | 21 | 0 | 11 |
| en | 0 | 0 | 0 | 46 | 0 | 9 | 0 | 0 |

Public-page checks after publication: PASSED 30. Public-page checks run after publication, back off and retry; they never stop the queue.

Session ledger hand-over: FAST_FORWARD (session v1327, shared v615)

Adapter: VERIFIED (live status is PENDING until a credentialed preflight succeeds)

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

- No external AI session lease; Actions do not generate prose
- The session ledger in this checkout is not in the shared ledger yet: the queue job (or `promote --apply`) hands it over

Existing articles are not attributed to ChatGPT or Claude without provenance. Live URL verification is not Google index verification.

## GitHub Actions

Status: UNKNOWN
