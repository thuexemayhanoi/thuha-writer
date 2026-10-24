#!/usr/bin/env python3
"""Submit three owner-requested original Vietnamese manuscripts via the REAL ThuHa Writer contracts.

No direct WordPress writes. The only WordPress publication route remains the
guarded native adapter publisher after fresh inventory, precheck, QA >=75,
zero hard-fails and a durable WordPress receipt. Idempotent on reruns.
"""
import argparse
import json
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from thuha import coordinator, quality, quota, runtime, writing
from thuha.cli import dispatch_qa_ready, inventory_for, live_counts
from thuha.common import ROOT, load, validate_inventory
from thuha.language import targets as language_targets
from thuha.store import GitStore

IDS = ("TH-VI-0008", "TH-VI-0090", "TH-VI-0224")
AGENT = "chatgpt-vi-writer-trial"
SESSION_PREFIX = "vi-writer-trial-20261024-"
SOURCE_COMMIT = os.environ.get("GITHUB_SHA") or writing.git_head()


def article_from_prepared(store, topic, inventory, policy, facts, session, tid):
    prepared = load(ROOT / "editorial" / "vi-trial" / (tid + ".json"))
    if (prepared.get("preparation_status") != "PREPARED_NOT_CLAIMED_OR_SUBMITTED"
            or prepared.get("topic_id") != tid or prepared.get("language") != "vi"):
        raise ValueError("Prepared content identity/status invalid: " + tid)
    if (topic["language"] != "vi" or prepared["title"] != topic["proposed_title"]
            or prepared["canonical"] != topic["proposed_url"]
            or prepared["category_id"] != topic["category_id"]
            or prepared["source_topic_id"] != tid):
        raise ValueError("Prepared text does not match authoritative VI topic: " + tid)
    pack = writing.pack(store, store.read(), inventory, tid, policy, facts)
    if not pack.get("skeleton"):
        raise ValueError("No admitted Writer skeleton: " + tid)
    if writing.stale_sources(pack):
        raise ValueError("First-party/source capture stale; recapture with official source command: " + tid)
    article = writing.compose(
        pack, prepared["body_html"],
        {"title": prepared["title"],
         "seo_title": prepared["seo_title"],
         "meta_description": prepared["meta_description"],
         "business_claims": [], "featured_media": None},
        session=session, agent_id=AGENT, source_commit=SOURCE_COMMIT,
    )
    if (article["language"] != "vi" or article["canonical"] != topic["proposed_url"]
            or article["category_id"] != topic["category_id"]
            or not article.get("sources")):
        raise ValueError("Native VI identity or source missing: " + tid)
    return article


def preview(store, inventory, policy, facts, tid):
    state = store.read()
    topic = state["topics"].get(tid)
    if not topic:
        return {"status": "SKIPPED_UNKNOWN_TOPIC"}
    if topic["status"] == "PUBLISHED" and tid in state["receipts"]:
        return {"status": "ALREADY_PUBLISHED", "wp_id": state["receipts"][tid]["wp_id"]}
    if topic["status"] != "PLANNED" or tid in state["submissions"]:
        return {"status": "SKIPPED_NOT_CLAIMABLE", "topic_status": topic["status"]}
    if any(lease["topic_id"] == tid for lease in state["leases"].values()):
        return {"status": "SKIPPED_LEASED"}
    session = SESSION_PREFIX + tid[-4:]
    article = article_from_prepared(store, topic, inventory, policy, facts, session, tid)
    result = runtime.precheck(store, state, inventory, tid, article, policy, facts)
    lint_fixes = [f["code"] for f in result["lint"] if f["severity"] == "fix"]
    return {"status": "WOULD_PASS" if result["ready_to_submit"] and result["would_pass_qa"] and not lint_fixes else "PRECHECK_NOT_PASS",
            "score": result["score"], "hard_fails": result["hard_fails"],
            "content_fails": result["content_fails"],
            "data_waits": result["data_waits"], "lint_fixes": lint_fixes,
            "ready_to_submit": result["ready_to_submit"]}


def apply_one(store, inventory, policy, facts, tid):
    check = preview(store, inventory, policy, facts, tid)
    if check["status"] != "WOULD_PASS":
        return check
    state = store.read()
    counts = live_counts(inventory, state)
    if counts is None:
        raise ValueError("Authenticated live count unavailable, refusing lease or submission")
    session = SESSION_PREFIX + tid[-4:]
    lease = coordinator.claim(store, session, AGENT, slot="auto",
                              ttl=1800, counts=counts, targets=language_targets(), pick=tid)
    try:
        state = store.read()
        article = article_from_prepared(store, state["topics"][tid], inventory, policy, facts, session, tid)
        again = runtime.precheck(store, state, inventory, tid, article, policy, facts)
        fixes = [f["code"] for f in again["lint"] if f["severity"] == "fix"]
        if not (again["ready_to_submit"] and again["would_pass_qa"]) or fixes:
            raise ValueError("Changed precheck after claim: " + ", ".join(again["hard_fails"] + fixes))
        coordinator.submit(store, lease["slot"], session, lease["fence"],
                           article, max_repairs=policy["maximum_repairs"])
        verified = quality.run_qa(store, tid, inventory, policy, facts)
        return {"status": verified["status"], "score": verified["score"],
                "hard_fails": verified["hard_fails"],
                "article_sha": verified["article_sha"]}
    except Exception:
        # A claim with no submission must not strand its lease if anything fails.
        state = store.read()
        if tid not in state["submissions"]:
            owned = state["leases"].get(lease["slot"])
            if owned and owned["session"] == session and owned["fence"] == lease["fence"]:
                coordinator.release(store, lease["slot"], session, lease["fence"])
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Perform real claims, submissions and unchanged QA")
    args = parser.parse_args()
    store = GitStore()
    policy, facts = load(ROOT / "config/qa.json"), load(ROOT / "config/business-facts.json")
    inv = inventory_for(store, None)
    validate_inventory(inv, policy["inventory_max_age_seconds"])
    if inv.get("language_source") != "adapter":
        raise ValueError("Verified authenticated bilingual adapter inventory required; no writing against public-only inventory")
    results = {}
    passed = []
    for tid in IDS:
        try:
            result = apply_one(store, inv, policy, facts, tid) if args.apply else preview(store, inv, policy, facts, tid)
        except Exception as exc:
            result = {"status": "ERROR", "error_type": type(exc).__name__, "reason": str(exc)[:250]}
        results[tid] = result
        if args.apply and result["status"] == "PASS":
            passed.append(tid)
    if args.apply and passed:
        # The existing guarded publisher is solely responsible for WordPress writes.
        results["publisher_trigger"] = dispatch_qa_ready(store, passed)
    print(json.dumps({"mode": "apply" if args.apply else "preview", "topics": results}, ensure_ascii=False, indent=2))
    # Fail visibly when not all articles made it through. Already-published topics
    # count as complete; do NOT create a second post.
    acceptable = {"PASS", "WOULD_PASS", "ALREADY_PUBLISHED"}
    return 0 if all(results[tid]["status"] in acceptable for tid in IDS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
