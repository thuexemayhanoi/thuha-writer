# Three native Vietnamese trial articles — prepared, not submitted

**Site:** https://rentbikehanoi.com · **Repository:** `thuexemayhanoi/thuha-writer` · **Created:** 2026-10-24

> **STATUS: EDITORIAL PREPARATION ONLY.** These files are NOT WordPress posts, do not exist in `factory-state` as article submissions, do not have QA reports or publication receipts, and must **not** be called READY/PUBLISHED. No claim, lease or idempotency key is fabricated. Never bypass the documented Writer → QA75 → adapter publisher pipeline to post them.

## Prepared drafts

| Topic | Exact planned article title | Body size (space-separated text units) | Same-language links |
| --- | --- | --- | --- |
| [TH-VI-0008](TH-VI-0008.json) | Nhóm bạn đi chung nhiều xe: cách chia tiền thuê xe, xăng và gửi xe cho công bằng | ~1,987 | 3 |
| [TH-VI-0090](TH-VI-0090.json) | Rủ người quen thạo xe đi cùng khi nhận xe: họ có thể giúp kiểm tra những gì | ~1,784 | 3 |
| [TH-VI-0224](TH-VI-0224.json) | Xe lúc có lúc không bị lỗi: ghi nhật ký ngày giờ, thời tiết và quãng đường để cửa hàng kiểm tra đúng chỗ | ~2,159 | 3 |

The topics were `PLANNED` with no active lease/submission at factory-state ledger **v623**, observed 24 Oct 2026. **Re-check live ledger and WordPress before proceeding**; this is a timestamped observation, not a reserved entitlement.

## Safe completion by an authorized Writer session

1. Start from **current** `AGENTS.md` and `docs/bilingual/CLAUDE-PROMPT.md`; follow [VI–EN QA contract](../../docs/bilingual/RENDERED-LANGUAGE-QA.md).
2. Read the current shared `factory-state` (do not trust the snapshot above). If working in a branch session, run `PYTHONPATH=src python3 -m thuha.cli --git-branch sync --apply` before claiming. Never overwrite a divergent ledger.
3. For each of the three exact topics, if still `PLANNED` and claimable, `claim --topic-id TH-VI-XXXX` with a genuine `session`, `agent-id` and valid lease/fence. Respect any new locks, collisions or updated topic assignments; skip ineligible topics.
4. Use `pack --topic-id TH-VI-XXXX` to retrieve actual source evidence, taxonomy, same-language **live** internal link catalogue, business facts, canonical and article skeleton. The prepared JSON contains **no** fake source capture, session, agent, source commit, lease, QA report or WordPress proof. Copy its `body_html` into a temporary `body.html`; fill actual pack metadata with its `seo_title`, `meta_description` and `focus_keyword`. Do not replace pack's canonical, category or source references if current live data differs.
5. Run the actual `build → precheck → submit` workflow. Repair all hard failures. Existing rules: **QA ≥75 with zero hard failures**, featured media optional, native VI only, two or more live same-language links including one live content page, official evidence for any regulated claim. If inventory is unusable, the genuine data-wait flow applies; do not invent a PASS.
6. Commit and hand off the session ledger via the normal fast-forward `promote` path; publisher alone may publish through the native VI adapter. After actual WordPress readback, verify public `/vi/` URL, HTML lang, title/meta, one matching H1 and publication receipt. Do not call these drafts published before that evidence exists.

## Business source and editorial boundaries

- Read current [`config/business-facts.json`](../../config/business-facts.json) for **Nguyễn Hà** only, not the separately operated Nguyễn Tú website. Existing topic state links its verified first-party source: `repo://config/business-facts.json`.
- Sample arithmetic in TH-VI-0008 is explicitly hypothetical, **not** an Nguyễn Hà price promise. Confirm real price with the rental shop before publishing any specific actual rental price.
- The manuscripts do not declare a deposit, return, delivery, repair or replacement policy. They offer reader checklists and questions rather than invented contractual commitments.
- External source citation was not added for general editorial guidance. If Writer introduces laws, legal obligations, model specifications or claims needing authoritative support, it must capture official evidence before submitting.
- Some same-language hyperlinks have been cross-checked against current WP Agent published-post listings, but the actual authenticated factory inventory remains the authority for eligibility.

## Intentional separation

The `editorial/vi-trial/` directory is excluded from factory-state drafts and actions. This prevents an experimental manuscript from being silently treated as QA-approved, from consuming a writer lease, or from publishing automatically. Do not edit existing WordPress posts, rename URLs or put provisional files into `drafts/vi/` as a substitute for a real `submit`.
