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

### Sau review biên tập độc lập lô #1 (23/10/2026)

Một tác tử khác (không phải người viết) đọc cả mười bản nháp đối chiếu với `config/business-facts.json`. Kết quả ban đầu: **0 bản sạch**,
2 lỗi chặn (cả hai là lỗi số học trong ví dụ của chính tôi: TH-VI-0019 nói chênh lệch "rất lớn" trong khi hai cách tính cùng ra 1.150.000 đồng cho đủ
mười ngày; TH-VI-0033 nói "ba tổng khác nhau" trong khi chỉ có hai tổng khác nhau), 48 chỗ cần sửa và 41 chỗ nhỏ. Điều được ghi nhận thẳng:

- Giọng văn: bản nháp để lộ ghi chú quy trình ("do chủ cửa hàng cung cấp", "chưa có thông tin xác nhận") và vài câu mang giọng đối đầu đặt ngay
  trên trang của cửa hàng. Đã thống nhất một giọng: "giá tham khảo của Thuê xe máy Nguyễn Hà" và "mỗi cửa hàng có cách làm riêng, hãy hỏi trực tiếp".
  **Chủ cửa hàng cần duyệt giọng này một lần cho cả loạt.**
- Trùng ý trong cụm cọc/đền bù và cụm ngày/tuần: đã phân lại phần của từng bài; TH-VI-0024 chỉ còn lặp TH-VI-0011 nên **bị giữ lại (`HELD`)**, ý riêng của
  nó (hỏi xem mức đền bù và cọc có khác nhau theo dòng xe không) nằm trong một mục của TH-VI-0011.
- Một số câu ngầm cho rằng cửa hàng có phiếu thuê, biên nhận, cọc: đã đổi thành "nếu có" hoặc thành lời đề nghị.
- Từ khóa chính chưa xuất hiện nguyên văn trong thân bài: đã đưa vào đoạn mở đầu; meta ≤155 ký tự.
- **Khoảng trống giá trị (chưa giải quyết được ở đây):** mọi bài đều là danh sách câu hỏi dành cho cửa hàng vì chủ cửa hàng chưa trả lời các
  câu hỏi đó. Chỉ chủ cửa hàng mới trả lời được. Xem "Dữ liệu cần từ chủ cửa hàng" trong `IMPLEMENTATION-STATUS.md`.
- **Rủi ro nội dung hàng loạt:** các bài cùng một khung (mở đầu - bảng câu hỏi - mẫu tin nhắn - đoạn liên hệ). Ở quy mô 500 bài điều này giống nội dung sản xuất
  hàng loạt. Vì vậy tôi **không viết thêm** hàng chục bài "hỏi cửa hàng" cùng khung khi chưa có dữ kiện của chủ cửa hàng hoặc nguồn ngoài.

Chín bản đã được viết lại và nộp lại (không tính là sửa lỗi: đó là hoàn thiện bản chờ dữ liệu); `TH-VI-0024` ở `HELD`.

## Lô VI #2 (23/10/2026)

Kiểm ý định độc lập: 8 DISTINCT, 2 OVERLAP (`TH-VI-0086` trùng 0101, `TH-VI-0211` trùng 0049). Hai chủ đề bị trùng **không nhập sổ cái**.
Tám bản nháp viết sau khi biết các phát hiện ở trên (cùng giọng văn, "nếu có", từ khóa trong thân bài) rồi lưu `WAITING_DATA`:
TH-VI-0043, 0053, 0063, 0089, 0093, 0095, 0101, 0217. Lỗi của chính tôi cần ghi lại: lần nộp đầu của lô #2 vô tình dùng văn bản cũ (trước khi áp dụng các bài học trên) vì một script phụ bỏ qua thư mục
bản đã sửa. Tôi phát hiện khi đối chiếu số liệu của bản đã lưu (meta quá dài, từ khóa vắng mặt), trước khi có reviewer nào đọc chúng; cả tám bản được nộp lại
như hoàn thiện bản chờ (không tốn lần sửa) và bản đã lưu nay khớp văn bản đã sửa. Review biên tập độc lập lần hai chạy trên bản đã lưu của cả 17 bài.

### Review biên tập lần hai và gộp bài (23/10/2026)

Review độc lập lần hai chạy trên cả 17 bản đã lưu. Kết quả nói thẳng: số liệu đã đúng (mọi tổng, mốc, bảng được tính lại), meta đã ≤155 ký tự, nhưng **giọng văn, khung bài và chồng lấn ý chưa được sửa**:
cả 17 bài cùng một khung (mở đầu bằng câu hỏi, lời rào "bài chỉ giúp bạn biết hỏi gì", bảng câu hỏi, mẫu tin nhắn, mục "Hỏi cửa hàng"), và chỉ năm bài dạy được điều gì ngoài danh sách câu hỏi.
Reviewer đề nghị xuất bản **7 trang thay vì 17**, và tôi làm theo vì đúng với quy tắc "một ý định tìm kiếm riêng cho mỗi bài" và không nhồi chữ:

| Trang giữ (WAITING_DATA) | Nhận thêm từ | Điều đã sửa |
|---|---|---|
| TH-VI-0019 ngày/tuần/tháng | 0006 trả sớm, 0063 tuần so với tháng | Sửa lỗi nhãn "cách 1/cách 2" (lỗi chặn); thêm bảng giá theo từng dòng xe có giá cố định (Vision, Air Blade, xe 50cc) |
| TH-VI-0004 cách đếm một ngày | | Nêu rõ quy tắc làm tròn phần lẻ mà cả bảng dựa vào; bỏ câu khái quát về thị trường |
| TH-VI-0033 hai khoản cọc | 0035 hoàn cọc, 0053 thuê hai xe | Một trang cọc duy nhất; bảng A/B/C sửa theo thời điểm trả tiền thuê; bỏ giọng đòi bằng chứng |
| TH-VI-0011 hiện trạng và đền bù | 0089 mức xăng/pin | Gỡ câu chỉ để mang con số giá; thêm ghi pin cho xe điện; sửa giọng "cửa hàng bạn chọn" |
| TH-VI-0093 trả muộn | 0101 trả sau giờ đóng cửa | Một trang cho "đến muộn hơn đã hẹn"; từ khóa vào thân bài |
| TH-VI-0058 sinh viên thuê tháng | 0095 cuối kỳ thuê | Thêm bảng ba tháng từ giá tham khảo; "nếu có" cho hợp đồng/phiếu |
| TH-VI-0016 giá trên Facebook | 0043 đối chiếu thông tin liên hệ | Thêm câu phạm vi (bài nhân danh Thuê xe máy Nguyễn Hà), bỏ đoạn tự bào chữa |

`HELD` (giữ nguyên bản đã lưu, có lý do, hoàn tác bằng `unhold`): 0006, 0063, 0035, 0053, 0089, 0101, 0095 (đã gộp); 0014 (danh sách câu hỏi không có đáp án hay phép tính), 0043 (bài cảnh báo lừa đảo là quyết định về giọng điệu của chủ cửa hàng), 0217 (kiểm toán hồ sơ bảo dưỡng của chính cửa hàng khi chưa biết gì về nó), cùng 0024 từ trước.
Không có bài nào trong số này bị xóa; chủ đề vẫn là dòng kế hoạch trong ma trận.

Điều chưa được giải quyết bằng viết lại: **giọng trung lập kiểu "hướng dẫn người tiêu dùng" đặt trên trang của chính cửa hàng**, và việc mọi bài vẫn trả lời "hãy hỏi cửa hàng". Gốc rễ là cửa hàng chưa trả lời các câu hỏi; reviewer cũng đề nghị chủ cửa hàng
xác nhận lại khoảng giá (xe số: giá tháng thấp hơn hai tuần; xe ga: giá tuần tối đa gấp hơn năm lần giá ngày thấp nhất). Cả hai nằm trong [OWNER-QUESTIONS.md](OWNER-QUESTIONS.md).
