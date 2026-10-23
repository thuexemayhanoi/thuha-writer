# Nhật ký viết bài (từng lô)

Nhật ký này ghi từng quyết định của phiên viết: chủ đề nào được nhận, chủ đề nào bị giữ lại và vì sao, bản thảo nằm ở đâu và đang ở trạng
thái nào. **Matrix là kế hoạch, bản thảo không phải bài đã xuất bản**: không dòng nào dưới đây là bài đã đăng. Sổ cái
(`data/state/factory.json` + `data/documents/`) là nguồn chính; `drafts/` là bản đọc được, sinh bằng `python3 scripts/export_drafts.py`.

Nguồn duy nhất đọc được trong môi trường viết này là tệp thông tin do chủ cửa hàng cung cấp (`config/business-facts.json`), được chụp thành
bằng chứng "first-party" có nhãn (`source --repository-file`). Mọi trang web bên ngoài (luật, nhà sản xuất, địa điểm, giao thông) không đọc
được từ container này (chỉ `api.github.com` tới được; WebFetch không phân giải được tên miền; Firecrawl hết tín dụng), nên **không có nguồn
ngoài nào được ghi là đã xác minh** và các chủ đề cần nguồn ngoài vẫn là `NEEDS_SOURCE`.

## Lô VI #1 (23/10/2026)

Chọn theo `write_order` trong các dòng chỉ cần `first_party_facts` (cộng `editorial_only`), rồi kiểm ý định độc lập (một tác tử khác, đọc toàn bộ
490 dòng còn lại của kế hoạch VI và 9 ứng viên còn lại).

| Chủ đề | Kết quả kiểm ý định | Trạng thái |
|---|---|---|
| TH-VI-0004 ngày thuê tính 24 giờ hay ngày lịch | DISTINCT | `WAITING_DATA`, bản thảo đã lưu |
| TH-VI-0006 trả xe sớm hơn dự kiến | DISTINCT | `WAITING_DATA` |
| **TH-VI-0010 báo giá đã gồm những gì** | **OVERLAP với TH-VI-0255** (cùng bộ mũ/áo mưa/khóa/giá đỡ, cùng lời giải "hỏi từng món"; truy vấn còn là thứ trang bảng giá/FAQ trả lời thẳng) | **Không nhập sổ cái.** Giữ nguyên là dòng kế hoạch; gộp vào 0255 hoặc đổi ý định rồi duyệt lại. Bản nháp đã viết không được lưu |
| TH-VI-0011 bảng mức đền bù trước khi nhận xe | DISTINCT | `WAITING_DATA` |
| TH-VI-0014 phụ phí cần hỏi | DISTINCT (phải giữ vai trò danh sách ngắn, liên kết ra các bài từng khoản khi chúng đã đăng) | `WAITING_DATA` |
| TH-VI-0016 giá tham khảo và bài đăng ưu đãi | DISTINCT | `WAITING_DATA` |
| TH-VI-0019 đổi từ gói ngày sang gói tuần | DISTINCT | `WAITING_DATA` |
| TH-VI-0024 cọc và đền bù theo loại xe | DISTINCT | `WAITING_DATA` |
| TH-VI-0033 cọc giữ chỗ và cọc nhận xe | DISTINCT | `WAITING_DATA` |
| TH-VI-0035 khi nào nhận lại tiền cọc | DISTINCT | `WAITING_DATA` |
| TH-VI-0058 tân sinh viên thuê xe theo tháng (thay cho 0010) | DISTINCT (không nêu giá, ưu đãi sinh viên, chính sách cửa hàng) | `WAITING_DATA` |

Mọi bản thảo trong lô thiếu đúng ba thứ và cả ba đều được ghi vào `waiting_for`: `FEATURED_MEDIA` (không ảnh nào có alt tiếng Việt),
`INTERNAL_LINKS` (chưa có trang/bài tiếng Việt nào còn sống để dẫn tới; trong bài chỉ có hai liên kết tới chuyên mục đã có trong manifest)
và `AUTHORITATIVE_INVENTORY` (chưa có inventory từ adapter). Chưa bản nào có review, QA hay biên nhận.
