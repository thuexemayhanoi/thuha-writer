#!/usr/bin/env python3
"""One-time factual, SEO-safe repair of seven Vietnamese posts that failed only live-link QA.

Do not change the QA threshold, WordPress posts, business policies or article sources.
Only authoritative factory-state entries are mutated; the guarded publisher owns WP writes.
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

SITE = "https://rentbikehanoi.com/vi/"
LINKS = {
    "TH-VI-0004": (
        ("thu-tuc-thue-xe-may-ha-noi/", "những điều cần chuẩn bị khi thuê xe"),
        ("lien-he/", "thông tin liên hệ để xác nhận giờ nhận và trả xe"),
    ),
    "TH-VI-0011": (
        ("thu-tuc-thue-xe-may-ha-noi/", "hướng dẫn chuẩn bị trước khi nhận xe"),
        ("lien-he/", "thông tin liên hệ để hỏi trực tiếp cửa hàng"),
    ),
    "TH-VI-0016": (
        ("bang-gia-thue-xe-may-ha-noi/", "bảng giá thuê xe máy tham khảo được công bố"),
        ("lien-he/", "kênh liên hệ chính thức để xác nhận giá và xe"),
    ),
    "TH-VI-0019": (
        ("bang-gia-thue-xe-may-ha-noi/", "khung giá ngày, tuần và tháng để đối chiếu"),
        ("thu-tuc-thue-xe-may-ha-noi/", "các bước cần trao đổi khi thuê xe"),
    ),
    "TH-VI-0033": (
        ("thu-tuc-thue-xe-may-ha-noi/", "những câu hỏi cần làm rõ trước khi thuê xe"),
        ("lien-he/", "cách liên hệ cửa hàng để xác nhận khoản cọc cụ thể"),
    ),
    "TH-VI-0058": (
        ("bang-gia-thue-xe-may-ha-noi/", "khung giá thuê xe theo ngày, tuần và tháng"),
        ("thue-xe-ga-ha-noi/", "các lựa chọn xe ga phù hợp để cân nhắc"),
    ),
    "TH-VI-0093": (
        ("lien-he/", "thông tin liên hệ cửa hàng để báo thay đổi giờ trả xe"),
        ("giao-nhan-xe-may-ha-noi/", "các bước giao nhận cần xác nhận từ trước"),
    ),
}

LEADS = {
    "TH-VI-0004": "Vì cách tính ngày thuê phụ thuộc thỏa thuận thực tế, hãy ghi rõ giờ bắt đầu và kết thúc trước khi quyết định:",
    "TH-VI-0011": "Đối với tình huống xe trầy xước hoặc phát sinh hư hỏng, hãy yêu cầu xác nhận mức xử lý theo trường hợp thực tế, không tự suy đoán:",
    "TH-VI-0016": "Để tránh nhầm giá tham khảo với ưu đãi trên mạng xã hội, hãy đối chiếu nội dung đã công bố và hỏi lại giá tại thời điểm đặt:",
    "TH-VI-0019": "Giá ngày, tuần và tháng là mức tham khảo; việc chuyển gói hay tính lại khoản đã thanh toán cần được cửa hàng xác nhận:",
    "TH-VI-0033": "Cọc giữ chỗ và cọc nhận xe không nên được xem là cùng một chính sách khi chưa có xác nhận cụ thể:",
    "TH-VI-0058": "Nếu thuê xe trong thời gian nhập học, hãy cân nhắc loại xe, thời hạn thuê và chi phí theo kế hoạch thực tế:",
    "TH-VI-0093": "Nếu lịch trả xe có nguy cơ thay đổi vì mưa hoặc tắc đường, hãy liên hệ trước và hỏi cách xử lý từng tình huống:",
}


def append_context(article, tid):
    draft = copy.deepcopy(article)
    a, b = LINKS[tid]
    if any(SITE+u in draft["body_html"] for u, _ in (a, b)):
        # Keep bounded and predictable: do not add the same link twice.
        raise ValueError("One of the planned links is already present: review manually " + tid)
    first = '<a href="' + SITE + a[0] + '">' + a[1] + '</a>'
    second = '<a href="' + SITE + b[0] + '">' + b[1] + '</a>'
    draft["body_html"] += "\n<p>" + LEADS[tid] + " xem " + first + " và " + second + ". Hãy xác nhận lại thông tin cụ thể trước khi quyết định.</p>"
    return draft


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args=parser.parse_args()
    store=GitStore()
    policy=load(ROOT/"config/qa.json")
    facts=load(ROOT/"config/business-facts.json")
    inv=inventory_for(store,None)
    validate_inventory(inv, policy["inventory_max_age_seconds"])
    if inv.get("language_source") != "adapter":
        raise ValueError("Need real authenticated Vietnamese inventory")
    live={urlkey(x["url"]) for x in inv["items"] if x.get("public_check",{}).get("http_status")==200 and item_language(x)=="vi"}
    for tid,pair in LINKS.items():
        for url,_ in pair:
            if urlkey(SITE+url) not in live:
                raise ValueError("Unverified live VI link: "+url)
    results={}
    passed=[]
    for tid in LINKS:
        s=store.read()
        t=s["topics"][tid]
        if t["status"] in ("READY","PUBLISHED"):
            results[tid]=t["status"]
            continue
        if t["status"]!="NEEDS_REPAIR" or s["qa"].get(tid,{}).get("status")!="FAIL":
            results[tid]="UNEXPECTED_STATE_"+t["status"]
            continue
        source=store.get_document(s["submissions"][tid]["article_sha"])
        draft=append_context(source, tid)
        original=s["submissions"][tid]
        anticipated=quality.evaluate(draft,t,{**original,"article_sha":digest(draft)},inv,policy,store,business=facts)
        if anticipated["status"]!="PASS":
            results[tid]={"status":"PRECHECK_FAILED","score":anticipated["score"],"hard_fails":anticipated["hard_fails"]}
            continue
        if not args.apply:
            results[tid]={"status":"WOULD_PASS","score":anticipated["score"]}
            continue
        session="vi-qa-links-20261024-"+tid[-4:]
        agent="chatgpt-seo-editor"
        lease=coordinator.claim(store,session,agent,pick=tid)
        draft.update(session=session, agent_id=agent, source_commit=os.environ.get("GITHUB_SHA",""))
        check=quality.evaluate(draft,store.read()["topics"][tid],
             {"session":session,"agent_id":agent,"article_sha":digest(draft)},inv,policy,store,business=facts)
        if check["status"]!="PASS":
            coordinator.release(store,lease["slot"],session,lease["fence"])
            results[tid]={"status":"POST_CLAIM_FAILED","hard_fails":check["hard_fails"]}
            continue
        coordinator.submit(store,lease["slot"],session,lease["fence"],draft,policy["maximum_repairs"])
        q=quality.run_qa(store,tid,inv,policy,facts)
        results[tid]={"status":q["status"],"score":q["score"],"hard_fails":q["hard_fails"]}
        if q["status"]=="PASS":passed.append(tid)
    if passed:
        results["dispatch"]=dispatch_qa_ready(store,passed)
    print(json.dumps({"mode":"apply" if args.apply else "preview","topics":results},ensure_ascii=False))
    return 0 if all(v in ("PUBLISHED","READY") or isinstance(v,dict) and v.get("status") in ("PASS","WOULD_PASS")
                    for k,v in results.items() if k!="dispatch") else 1

if __name__=="__main__":
    raise SystemExit(main())
