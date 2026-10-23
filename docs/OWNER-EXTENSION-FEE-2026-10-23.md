# Owner-confirmed extension fee — 23 October 2026

Only website: https://rentbikehanoi.com. Date uses Asia/Ho_Chi_Minh.

The owner explicitly confirmed: **Phí gia hạn 20.000đ/giờ; quá 6 giờ tính một ngày thuê.**
English: **Extension fee: 20,000 VND per hour. More than 6 hours is charged as one rental day.**

The daily-charge threshold is strictly greater than 6 hours (`>6`), not `>=6`.
The old 30,000 VND/hour rate and a limitation to 1-5 hours are superseded.
Do not invent a new daily rental price, deposit/refund policy or another threshold.

`config/business-facts.json extension_policy` is the machine-readable first-party fact.
Extension charges are no longer in `unconfirmed_policies`; delivery and deposit procedures/refunds remain unconfirmed.
The bilingual writing pack exposes the confirmed policy without changing QA points, thresholds or hard failures.
Recapture first-party evidence from the updated facts file before using it in a new/revised submission; old immutable
source documents and ledger history must never be rewritten to pretend they were captured from the new file.

An authorized assistant updated exactly the extension passages in existing WordPress bodies 67, 211, 274, 278, 283 and 289.
Read-back confirmed all six remain published, contain the correct hourly fee and greater-than-six-hour threshold, and no longer
contain the old exact-six-hour ambiguity. A read-only scan for 30,000/30.000 near an hourly unit returned no published post/page matches.
LiteSpeed/object cache was purged. Unrelated 30,000 VND prices were not replaced. Native Vietnamese config already matched.
This is a live content correction, not a factory publication receipt, theme deployment, new article or QA exception.
