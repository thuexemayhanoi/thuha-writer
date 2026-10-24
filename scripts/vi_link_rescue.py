#!/usr/bin/env python3
"""One-time, evidence-based repair of two Vietnamese drafts stuck on links to unpublished articles.

Never relax QA, fabricate live URLs, overwrite the ledger, or write to WordPress.
The existing guarded publisher alone creates WordPress posts after a real QA PASS.
Usage: PYTHONPATH=src python3 scripts/vi_link_rescue.py [--apply]
"""
import argparse
import copy
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from thuha import coordinator, quality
from thuha.cli import dispatch_qa_ready, inventory_for
from thuha.common import ROOT, digest, load, urlkey, validate_inventory
from thuha.research import item_language
from thuha.store import GitStore

PRICE_PAGE = "https://rentbikehanoi.com/vi/bang-gia-thue-xe-may-ha-noi/"
CATEGORY = "https://rentbikehanoi.com/vi/chuyen-muc/gia-thue-va-chi-phi/"

PATCHES = {
    "TH-VI-0018": [
        (
            'theo gợi ý trong bài <a href="https://rentbikehanoi.com/vi/lau-roi-khong-cam-lai-tap-lai-thang-bang-phanh-va-quay-dau/">lâu rồi không cầm lái</a>',
            "rồi tăng dần độ khó ở nơi vắng trước khi tham gia giao thông đông đúc",
        ),
        (
            'như bài <a href="https://rentbikehanoi.com/vi/di-choi-trong-ngay-bang-nhieu-xe-thu-tu-chay-diem-dung-chung/">đi chơi trong ngày bằng nhiều xe</a> hướng dẫn',
            "nên cần thống nhất điểm hẹn và cách liên lạc từ trước",
        ),
        (
            'Muốn so thêm với việc gọi xe, hãy dùng cách tính trong bài <a href="https://rentbikehanoi.com/vi/di-it-chang-trong-ngay-khi-nao-goi-xe-cong-nghe-hop-hon-thue-xe-may/">đi ít chặng trong ngày, khi nào gọi xe công nghệ hợp hơn thuê xe máy</a>',
            "Muốn so thêm với việc gọi xe, hãy đếm đủ lượt đi về và tính tổng chi phí từng phương án",
        ),
    ],
    "TH-VI-0022": [
        (
            'bài <a href="https://rentbikehanoi.com/vi/di-hai-nguoi-thue-mot-xe-hay-hai-xe-can-nhac-gi/">đi hai người thuê một xe hay hai xe</a> tính tiếp theo cùng cách này',
            "hãy đưa chi phí của xe thứ hai vào phép so sánh thay vì chỉ tính số chuyến",
        ),
    ],
}

APPENDICES = {
    "TH-VI-0018": (
        '<p>Để so sánh chi phí thuê một xe và hai xe theo số ngày thực tế, '
        '<a href="' + PRICE_PAGE + '">xem bảng giá thuê xe máy Hà Nội</a>, '
        'sau đó xác nhận lại mẫu xe và mức giá trước khi đặt.</p>'
    ),
    "TH-VI-0022": (
        '<p>Để thay số liệu giả định bằng khung giá thuê tham khảo đã công bố, '
        '<a href="' + PRICE_PAGE + '">xem bảng giá thuê xe máy Hà Nội</a> '
        'và xác nhận lại mẫu xe cùng mức giá trước khi đặt.</p>'
    ),
}


def preview_rewrite(article, tid):
    candidate = copy.deepcopy(article)
    body = candidate["body_html"]
    for old, new in PATCHES[tid]:
        if body.count(old) != 1:
            raise ValueError("Expected exactly one editorial phrase for " + tid)
        body = body.replace(old, new, 1)
    if PRICE_PAGE in body:
        raise ValueError("Page link already present; review manually before another edit")
    body += "\n" + APPENDICES[tid]
    candidate["body_html"] = body
    return candidate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Authorize guarded ledger revisions and QA")
    args = parser.parse_args()
    store = GitStore()
    policy = load(ROOT / "config/qa.json")
    facts = load(ROOT / "config/business-facts.json")
    inv = inventory_for(store, None)
    validate_inventory(inv, policy["inventory_max_age_seconds"])
    if inv.get("language_source") != "adapter":
        raise ValueError("Authenticated bilingual inventory is mandatory")
    live = {urlkey(x["url"]): x for x in inv["items"] if x.get("public_check", {}).get("http_status") == 200 and item_language(x) == "vi"}
    archives = {urlkey(c["link"]) for c in inv["categories"] if c.get("language") == "vi" and c.get("link")}
    if urlkey(PRICE_PAGE) not in live or urlkey(CATEGORY) not in archives:
        raise ValueError("The real Vietnamese price page and category must already be verified live")

    passed = []
    outcome = {}
    for tid in PATCHES:
        state = store.read()
        topic = state["topics"].get(tid)
        if not topic or topic["language"] != "vi":
            raise ValueError("Wrong language or unknown topic " + tid)
        if topic["status"] == "PUBLISHED":
            outcome[tid] = "ALREADY_PUBLISHED"
            continue
        if not (topic["status"] == "DRAFT_READY" and state["qa"].get(tid, {}).get("status") == "BLOCKED_DATA"):
            outcome[tid] = "NOT_IN_EXPECTED_BLOCKED_DATA_STATE"
            continue
        sub = state["submissions"][tid]
        original = store.get_document(sub["article_sha"])
        updated = preview_rewrite(original, tid)
        # A read-only real QA check before taking a lease. No policy exceptions.
        hypothetical = {**sub, "article_sha": digest(updated)}
        verdict = quality.evaluate(updated, topic, hypothetical, inv, policy, store, business=facts)
        if verdict["status"] != "PASS":
            outcome[tid] = {"status": "PRECHECK_NOT_PASS", "score": verdict["score"], "hard_fails": verdict["hard_fails"]}
            continue
        if not args.apply:
            outcome[tid] = {"status": "WOULD_PASS", "score": verdict["score"], "hard_fails": []}
            continue
        session = "vi-link-rescue-20261024-" + tid[-4:]
        agent = "chatgpt-editorial-link-rescue"
        lease = coordinator.claim(store, session, agent, revise=tid)
        updated.update({"session": session, "agent_id": agent, "source_commit": os.environ.get("GITHUB_SHA", "")})
        # The author attribution and session become the true owned lease; check again.
        latest = store.read()
        sub_preview = {"article_sha": digest(updated), "session": session, "agent_id": agent}
        check = quality.evaluate(updated, latest["topics"][tid], sub_preview, inv, policy, store, business=facts)
        if check["status"] != "PASS":
            coordinator.release(store, lease["slot"], session, lease["fence"])
            outcome[tid] = {"status": "POST_CLAIM_PRECHECK_FAIL", "hard_fails": check["hard_fails"]}
            continue
        coordinator.submit(store, lease["slot"], session, lease["fence"], updated, policy["maximum_repairs"])
        actual = quality.run_qa(store, tid, inv, policy, facts)
        outcome[tid] = {"status": actual["status"], "score": actual["score"], "hard_fails": actual["hard_fails"]}
        if actual["status"] == "PASS":
            passed.append(tid)
    if passed:
        outcome["dispatch"] = dispatch_qa_ready(store, passed)
    print(json.dumps({"mode": "apply" if args.apply else "preview", "topics": outcome}, ensure_ascii=False))
    return 0 if all(v in ("ALREADY_PUBLISHED", "NOT_IN_EXPECTED_BLOCKED_DATA_STATE") or isinstance(v, dict) and v.get("status") in ("PASS", "WOULD_PASS") for k,v in outcome.items() if k != "dispatch") else 1


if __name__ == "__main__":
    raise SystemExit(main())
