# Phase 01 — Reference Architecture and Live WordPress Audit

Date: 2026-10-21 (Asia/Bangkok/Asia/Ho_Chi_Minh)  
Scope: READ ONLY; no WordPress changes; no scheduled GitHub publishing.  
Target website: https://rentbikehanoi.com  
Reference: https://github.com/thuexemayhanoi/wp-writer  
New project: https://github.com/thuexemayhanoi/thuha-writer

## A. Reference repository: architecture assessment

The reference Git tree `main` was inspected recursively. It contains **1,126 tracked files** (source code, content, research, reports and state) and **20 workflow YAML files** under `.github/workflows`. The entire workflow YAML set was read, as were the core production policy, QA rules, coordinator/lease, publisher, taxonomy, research intake, intent, recovery and post-publish QA implementation files. This is a technical review, not a claim to have manually validated every line of all 1,126 files.

Promising patterns worth reimplementing independently:
- Claim + lease + heartbeat for W1–W9; immutable submission hashes.
- Topic research intake, factual provenance and search-intent collision checking.
- Exact live WordPress term ID, slug and parent-path mapping; category holds on ambiguity.
- Separate pre-publication hard gates and post-publication readback.
- Durable publisher ledger and reconciliation of uncertain WordPress responses.
- Paused/emergency stop policy, concurrency guards, provenance-specific receipts.

Findings that prohibit direct cloning:
1. **Wrong configured target:** reference `config/production-policy.json` currently declares `https://thuexemaynguyentu.com`, not `https://rentbikehanoi.com`.
2. **Live publishing by default:** `production_enabled=true`, `paused=false`, `emergency_stop=false`; this must never migrate unchanged.
3. **Repository-specific workflow filters:** existing jobs explicitly check `github.repository == 'thuexemayhanoi/wp-writer'`, and reference `wordpress-production` credentials. These do not belong in the new project unchanged.
4. **QA documentation drift:** reference `config/qa-rules.json` and `docs/ARTICLE-CONTRACT.md` use minimum 76 for SEO and quality, while publisher/workflow comments still mention 85. The active threshold and hard gates must be independently specified and tested.
5. **Target-specific taxonomy and language:** reference content manifest and taxonomy contain historical site identity, category IDs and Vietnamese examples. The new system must derive English editorial identities and category mappings from the live target WordPress site.
6. **Approval/security mismatch risk:** reference policy shows `security_controls_verified=false` while `production_enabled=true`. The new publisher must remain OFF until security checks pass.
7. **AI execution limitation:** scheduled GitHub Actions coordinate code and assets; they do not supply free, autonomous AI writing capability without a real accessible model/session.
8. **Large mutable state:** blindly copying reference ledgers, leases, receipts or topic IDs could cause duplicates or ghost claims against a different WordPress site.

## B. Live website findings — representative sample, not full audit

Authenticated WordPress REST API and WP Agent returned a consistent sample of the **30 most recent published posts**.

- **30/30** had SEO titles and meta descriptions.
- **30/30** showed `featured_media=0` / no featured image.
- **30/30** lacked an exposed Yoast focus keyword in the SEO overview.
- Published posts in the sample had canonical/index directives via Yoast. This was inspected on sample entries, NOT all site URLs.
- Public categories included hierarchy: `Blog` -> `Tips & Resources` -> `Motorbike Rental Guides`, `Parking, Weather & Breakdowns`, `Bike Setup & Everyday Use`, and `Blog` -> `Travel Guide` -> `Hanoi Routes & Sightseeing`, `Day Trips from Hanoi`, etc.
- Absence of the Yoast focus keyword is an editorial-tooling gap, not by itself evidence of poor Google rankings.
- A featured image is a separate WordPress property; some posts may still have images in their body or a fallback open-graph image.

Detailed sample WP Agent scores (agent heuristic, **not Google or Yoast scores**):

| WordPress ID | Topic | On-page SEO | Content quality | Principal issues |
|---|---|---:|---:|---|
| 3385 | Crossing Vietnam border with rental bike | 68 | 93 | Missing featured image, lengthy title, heading structure |
| 3384 | Replacing rental accessory | 67 | 80 | Missing featured image, no in-body internal links per analyzer, heading structure |
| 3376 | Che sen / che do den | 72 | 69 | Featured image, heading structure, actionable value |
| 3359 | Rental motorbike for delivery work | 65 | 73 | Featured image, heading structure, more helpful structured content |

Sample article URLs:
- https://rentbikehanoi.com/taking-a-rental-motorbike-across-a-vietnam-border-why-permission-alone-is-not-enough/
- https://rentbikehanoi.com/replacing-a-rental-motorbike-accessory-obtain-approval-before-you-buy/
- https://rentbikehanoi.com/che-sen-and-che-do-den-read-a-hanoi-dessert-menu/
- https://rentbikehanoi.com/motorbike-rental-for-delivery-work-in-hanoi-check-commercial-use-permission/

## C. Priority risk register

| Priority | Risk | Phase 1 action / planned gate |
|---|---|---|
| P0 | Accidentally publishing to wrong domain or duplicate URL | Freeze publishing; explicit target `rentbikehanoi.com` and live inventory gate |
| P0 | Reference workflow credentials or secrets accidentally copied | Start with empty safe config, no secrets, no privileged Actions |
| P0 | WordPress posts already published outside new repo | Build read-only inventory first; reconcile all historical IDs, slugs, canonicals before first POST |
| P1 | Featured image coverage 0/30 in sample | Report and prioritize media QA; do not mass-insert arbitrary images |
| P1 | Weak in-body linking and article structure in some posts | Report individual gaps; no bulk replacement of post HTML |
| P1 | Reference QA thresholds conflict in prose/config | Define one authoritative policy and test it before activation |
| P1 | Language/category drift from legacy Vietnamese manifests | English-only editorial contract, map to existing live category IDs |
| P2 | Focus keywords absent from 30 recent posts | Treat as Yoast editorial coverage, not an indexing guarantee |
| P2 | Incorrect claims about session activity or published counts | Distinguish agent claims, verified receipts, WordPress live status |

## D. Deliberate limitations

This phase has **not** established a complete count of all WordPress posts, images, in-body links, canonical collisions or Google indexing status. No Search Console performance measurements are implied. Do not claim any specific number of outstanding articles until a fresh full-site inventory and independent post/receipt reconciliation are complete.

No WordPress or reference-repository edits were performed. This new repository contains audit documentation and deliberately inactive configuration only.
