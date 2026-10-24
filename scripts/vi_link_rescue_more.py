#!/usr/bin/env python3
"""Curated second wave of Vietnamese link repairs.

Only full paragraphs that cite not-yet-published posts are replaced.
Live links and factual content remain; all QA hard gates stay in force.
This file cannot publish to WordPress: the guarded publisher owns that step.
"""
import vi_link_rescue as rescue

P = "https://rentbikehanoi.com/vi/"
PARAGRAPHS = {
    "TH-VI-0134": [
        ("<p>Nếu bạn chọn xe số hoặc xe côn tay,",
         '<p>Nếu chưa từng lái côn tay, đừng chọn chuyến chở người thân làm buổi tập đầu tiên. Hãy tự đánh giá khả năng điều khiển ở nơi an toàn và hỏi rõ mẫu xe trước khi đặt. Nếu xe côn chưa phù hợp, tham khảo <a href="' + P + 'thue-xe-ga-ha-noi/">lựa chọn xe ga tại Hà Nội</a> và <a href="' + P + 'thu-tuc-thue-xe-may-ha-noi/">các bước chuẩn bị thuê xe</a>. Chỉ chọn mẫu xe bạn điều khiển tự tin; không nên thuê chỉ vì bạn bè muốn thử.</p>'),
    ],
    "TH-VI-0146": [
        ("<p>Trên nhiều mẫu xe số, xích truyền động",
         '<p>Trên một số mẫu xe số, dây giày dài hoặc quai dép lỏng có thể vướng gần cần số và gác chân. Vì vậy, hãy buộc gọn dây giày, chọn giày ôm chân và thử thao tác lên xuống số ở nơi an toàn trước khi khởi hành. Gấu quần rộng cũng nên được giữ gọn để không vướng vào các bộ phận chuyển động.</p>'),
        ("<p>Nếu sau mười phút bạn vẫn thấy chân trái",
         '<p>Nếu sau khi thử bạn thấy thao tác gạt số chưa thoải mái, hãy cân nhắc mẫu xe dễ làm quen hơn thay vì cố dùng xe côn tay cho cả chuyến. Có thể <a href="' + P + 'thue-xe-ga-ha-noi/">tham khảo các lựa chọn xe ga</a> hoặc xem các chủ đề liên quan trong <a href="' + P + 'chuyen-muc/xe-so-va-xe-con/">chuyên mục xe số và xe côn</a>. Ưu tiên khả năng kiểm soát xe hơn hình thức của đôi giày.</p>'),
    ],
    "TH-VI-0151": [
        ("<p>Dù xe số hay xe ga, buổi đầu",
         '<p>Dù chọn xe số hay xe ga, nếu bố mẹ đã lâu không chạy xe thì nên thử lại thao tác ở nơi vắng, không chọn đường đông và không cố đi xa trong lần đầu. Hãy so sánh cách điều khiển của từng loại và sự thoải mái thực tế. Tham khảo <a href="' + P + 'thue-xe-ga-ha-noi/">các mẫu xe ga cho thuê</a> và <a href="' + P + 'bang-gia-thue-xe-may-ha-noi/">bảng giá thuê xe máy Hà Nội</a> trước khi xác nhận loại xe, thời gian và mức giá.</p>'),
    ],
    "TH-VI-0158": [
        ("<p>Nếu bạn chưa từng lái xe côn tay,",
         '<p>Nếu bạn chưa từng lái côn tay thì không nên chọn đúng chuyến chở người thân làm buổi tập đầu tiên. Trước khi nhận xe, hãy thử ở nơi an toàn để biết mình có sang số và dừng êm hay không. Nếu xe số không phù hợp, hãy <a href="' + P + 'thue-xe-ga-ha-noi/">tham khảo xe ga</a> và xem <a href="' + P + 'chuyen-muc/xe-so-va-xe-con/">chuyên mục xe số và xe côn</a> để cân nhắc theo khả năng thật, không phải theo thói quen của người khác.</p>'),
    ],
    "TH-VI-0267": [
        ("<p>Nếu hằng ngày bạn mặc váy,",
         '<p>Nếu mặc váy, áo dài hoặc quần ống rộng khi đi làm, hãy giữ gọn vạt áo và gấu quần để tránh vướng vào bánh xe và gác chân. Với kế hoạch đi làm dài ngày, ngoài chỗ cất áo mưa và giày thay, nên so chi phí theo tuần và tháng trong <a href="' + P + 'bang-gia-thue-xe-may-ha-noi/">bảng giá thuê xe máy Hà Nội</a>, xác nhận giá cụ thể trước khi đặt. Các hướng dẫn chuẩn bị đồ dùng nằm trong <a href="' + P + 'chuyen-muc/hanh-ly-va-phu-kien/">chuyên mục Hành lý và phụ kiện</a>.</p>'),
    ],
    "TH-VI-0268": [
        ("<p>Bộ đồ đẹp thường đi cùng đôi giày",
         '<p>Với váy dài hoặc áo dài, đôi giày cao gót và dép mỏng có thể làm việc chống chân khó hơn. Khi có thể, hãy chọn giày bệt ôm chân, mang giày diện riêng để thay ở điểm đến và giữ gấu quần, vạt áo gọn. Nếu đi xe số, hãy thử thao tác gạt số ở nơi an toàn với chính đôi giày bạn sẽ dùng trong chuyến đi.</p>'),
        ("<p>Có những dịp bộ đồ quá cầu kỳ",
         '<p>Nếu bộ đồ quá cầu kỳ để mặc nguyên khi đi xe, có thể mặc đồ gọn lúc di chuyển và thay trang phục ở nơi đến nếu có chỗ phù hợp. Bạn cũng có thể cân nhắc <a href="' + P + 'thue-xe-ga-ha-noi/">các lựa chọn xe ga</a> khi cần chỗ để chân và cách sử dụng khác xe số. Các cách chuẩn bị túi, áo mưa và phụ kiện nằm trong <a href="' + P + 'chuyen-muc/hanh-ly-va-phu-kien/">chuyên mục Hành lý và phụ kiện</a>.</p>'),
    ],
    "TH-VI-0359": [
        ("<p>Ngày đầu, hãy đặt kế hoạch đơn giản:",
         '<p>Ngày đầu quay lại lái xe, hãy đặt kế hoạch ngắn, tránh nhiều ngã rẽ phức tạp và tập dừng, quay đầu ở nơi phù hợp trước khi vào phố đông. Khi chưa tự tin, đừng lên đường dài chỉ để thử khả năng. Trước khi quyết định loại xe, có thể <a href="' + P + 'thue-xe-ga-ha-noi/">so sánh các lựa chọn xe ga</a>; các hướng dẫn liên quan đến mặt đường và thời tiết được tổng hợp tại <a href="' + P + 'chuyen-muc/thoi-tiet-va-ky-nang/">chuyên mục Thời tiết và kỹ năng</a>.</p>'),
    ],
    "TH-VI-0371": [
        ("<p>Trước khi lên cung đường dài,",
         '<p>Trước khi đi cung đường dài, hãy thử thao tác giảm tốc, quan sát hướng cua và giữ làn đường ở nơi phù hợp, không lấy đoạn đê đông xe làm nơi tập. Nếu đã lâu không chạy xe, nên bắt đầu bằng cung đường ngắn và chiếc xe quen tay. Có thể <a href="' + P + 'thue-xe-ga-ha-noi/">tham khảo các lựa chọn xe ga</a> trước chuyến đi; những chủ đề về mặt đường và thời tiết nằm tại <a href="' + P + 'chuyen-muc/thoi-tiet-va-ky-nang/">chuyên mục Thời tiết và kỹ năng</a>.</p>'),
    ],
    "TH-VI-0459": [
        ("<p>Muốn chốt điểm đến và phân xe",
         '<p>Trước khi xuất phát, nhóm nên chốt điểm đến, số xe, người lái và một điểm hẹn phòng trường hợp mất liên lạc. Nếu thuê nhiều xe, hãy thống nhất việc nhận và trả xe ngay từ khâu chuẩn bị; tham khảo <a href="' + P + 'giao-nhan-xe-may-ha-noi/">hướng dẫn giao nhận xe máy thuê</a> để biết các câu hỏi cần đặt cho cửa hàng. Những gợi ý sắp xếp lịch trình khác nằm trong <a href="' + P + 'chuyen-muc/di-choi-trong-ngay/">chuyên mục Đi chơi trong ngày</a>.</p>'),
    ],
    "TH-VI-0484": [
        ("<p>Khi đã có điểm đến, hãy chia xe",
         '<p>Khi đã chốt điểm đến, hãy thống nhất số xe, ai lái, ai ngồi sau và một điểm dừng chung nếu các xe tách nhau. Người ít kinh nghiệm nên chọn cách di chuyển phù hợp với khả năng và không cần cố tự lái chỉ vì cả nhóm đều đi xe riêng. Ghi lại điểm hẹn và số liên lạc trước khi xuất phát để mọi người vẫn tìm được nhau khi điện thoại mất mạng.</p>'),
        ("<p>Muốn cân nhắc thêm việc bỏ bớt điểm",
         '<p>Nếu chỉ có một ngày, hãy chọn ít điểm dừng nhưng đủ thời gian nghỉ và nhận, trả xe như kế hoạch. Trước khi chốt giờ xuất phát, xem <a href="' + P + 'giao-nhan-xe-may-ha-noi/">hướng dẫn giao nhận xe máy thuê</a> để biết những điều cần xác nhận với cửa hàng; những ý tưởng lập kế hoạch nằm trong <a href="' + P + 'chuyen-muc/lap-ke-hoach-chuyen-di/">chuyên mục Lập kế hoạch chuyến đi</a>.</p>'),
    ],
    "TH-VI-0487": [
        ("<p>Nếu bạn đi cùng bạn bè và chưa thống nhất",
         '<p>Nếu nhóm bạn chưa thống nhất điểm đến, hãy chốt một điểm quan trọng nhất rồi chỉ thêm điểm phụ khi còn thời gian. Trước lúc đi, ghi sẵn số liên lạc và thống nhất nơi gặp lại nếu điện thoại hết pin. Khi thuê xe, tính cả thời gian nhận và trả theo <a href="' + P + 'giao-nhan-xe-may-ha-noi/">các bước giao nhận xe cần hỏi</a>. Có thêm gợi ý sắp xếp chuyến đi trong <a href="' + P + 'chuyen-muc/lap-ke-hoach-chuyen-di/">chuyên mục Lập kế hoạch chuyến đi</a>.</p>'),
    ],
    "TH-VI-0491": [
        ("<p>Để chuyến đi trong ngày không biến",
         '<p>Trước chuyến đi xa, hãy viết sẵn địa chỉ nơi lưu trú, một điểm hẹn và số điện thoại liên lạc vào giấy. Nếu dùng xe thuê, lưu cả thông tin liên hệ cửa hàng được công bố tại <a href="' + P + 'lien-he/">trang liên hệ Thuê xe máy Nguyễn Hà</a> để có thể tra cứu khi cần. Các hướng dẫn chuẩn bị hành trình khác nằm trong <a href="' + P + 'chuyen-muc/lap-ke-hoach-chuyen-di/">chuyên mục Lập kế hoạch chuyến đi</a>.</p>'),
    ],
}


def rewrite(article, tid):
    from copy import deepcopy
    result = deepcopy(article)
    lines = result["body_html"].split("\n")
    for prefix, replacement in PARAGRAPHS[tid]:
        matches = [i for i, line in enumerate(lines) if line.startswith(prefix)]
        if len(matches) != 1:
            raise ValueError("Expected one editorial paragraph for " + tid + " starting with " + prefix)
        lines[matches[0]] = replacement
    result["body_html"] = "\n".join(lines)
    return result


def main():
    # Recover only our own orphaned claim after an interrupted GitHub document write.
    # A claim held by another session is never touched.
    import sys
    if "--apply" in sys.argv:
        from thuha import coordinator
        store = rescue.GitStore()
        state = store.read()
        for tid in PARAGRAPHS:
            if state["topics"][tid]["status"] != "CLAIMED":
                continue
            lease = next((v for v in state["leases"].values() if v["topic_id"] == tid), None)
            session = "vi-link-rescue-20261024-" + tid[-4:]
            if lease and lease["session"] == session and lease["agent_id"] == "chatgpt-editorial-link-rescue":
                if state["submissions"][tid]["article_sha"] == state["qa"][tid]["article_sha"]:
                    coordinator.release(store, lease["slot"], lease["session"], lease["fence"])
                else:
                    raise ValueError("Claim recovery refused: article changed while interrupted " + tid)
    # Reuse claim, immutable document, unchanged QA and dispatch implementations.
    rescue.PATCHES = {tid: [] for tid in PARAGRAPHS}
    rescue.preview_rewrite = rewrite
    return rescue.main()


if __name__ == "__main__":
    raise SystemExit(main())
