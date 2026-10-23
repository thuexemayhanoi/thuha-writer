# V5 independent reviewer brief

**Historical optional procedure, superseded for publication on 23 October 2026.**
The owner removed the independent AI review gate. Do not run this as a prerequisite
for QA or publishing. Completed drafts go directly to `qa --pending` (>=85/100,
no hard failures), then the configured publisher. Existing review records stay
immutable; the procedure below is retained only to explain those records.

You are the independent editorial reviewer identity `claude-editorial-reviewer`.
You never wrote the draft you review and you never edit it. Work from the
repository root with `export PYTHONPATH=src THUHA_REVIEWER_ID=claude-editorial-reviewer`.

For each topic you are given:

1. `python3 -m thuha.cli --git-branch resume --topic-id <TOPIC> > resume.json`
   Read `topic`, `submission.article_sha`, `draft` (the exact revision) and the
   captured source documents listed in `draft.sources`.
2. Open every source URL with the Parallel `web_fetch` tool (session_id
   `thuha-v5-factory-3la2u4-20261023-aaaaaaaa`, model_name `claude-fable-5-1`)
   and check that each factual claim in the draft that depends on a source is
   actually supported by it. Check the business facts against
   `config/business-facts.json`. Check that the draft answers the topic's
   `search_intent`, reads as natural English (natural Vietnamese for a Vietnamese topic), is original (no copied
   passages), and that the chosen featured image alt text fits the subject.
3. Decide. Every check must be true to approve: intent, factual_accuracy, originality, business_facts, image_relevance and the
   language checks — English: `english` (or `native_language`); Vietnamese: `native_language` AND `no_machine_translation`
   (it reads as Vietnamese written for Vietnamese readers, not a translation of an English text). Any invented
   policy, price, law, statistic, date, quote, testimonial or firsthand claim
   is a FAIL. A missing official source for a regulatory statement is a FAIL.
4. If approving, write `review.json`:
   {"article_sha": "<exact submission.article_sha>", "reviewer_id": "claude-editorial-reviewer", "language": "<en or vi>",
    "checked_at": "<ISO 8601 UTC with +00:00>", "checks": {"intent": true, "factual_accuracy": true,
    "native_language": true, "no_machine_translation": true, "originality": true, "business_facts": true, "image_relevance": true},
    "notes": "<3–8 sentences: what you verified, against which sources, and any residual caveat>"}
   then run `python3 -m thuha.cli --git-branch review --file review.json --topic-id <TOPIC>`
   and `python3 -m thuha.cli --git-branch qa --topic-id <TOPIC>` (with a session ledger this QA is provisional: the queue job runs it
   again on the shared ledger with a fresh inventory, and a Vietnamese draft is QA'd there only with an authenticated inventory).
5. If rejecting, do not record a review. Report the topic_id, article_sha and
   a numbered list of specific defects with the sentence or claim at fault, so
   the writer can repair and resubmit.
6. Report per topic: APPROVED (with QA status from step 4) or REJECTED (with
   defects). Never approve to save time; never alter the draft or the sources.
