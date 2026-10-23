# Nhật ký viết bài (từng lô)

Nhật ký này ghi từng quyết định của phiên viết: chủ đề nào được nhận, chủ đề nào bị giữ lại và vì sao, bản thảo nằm ở đâu và đang ở trạng
thái nào. **Matrix là kế hoạch, bản thảo không phải bài đã xuất bản**: không dòng nào dưới đây là bài đã đăng. Sổ cái
(`data/state/factory.json` + `data/documents/`) là nguồn chính; `drafts/` là bản đọc được, sinh bằng `python3 scripts/export_drafts.py`.

**Về chữ "review" trong nhật ký này:** các vòng "review biên tập" dưới đây là những lần đọc soát chất lượng tôi nhờ chạy *trong lúc viết* (tìm lỗi số học, lặp ý, giọng văn,
bài trùng ý). Chúng không phải cổng QA hay xuất bản, không ghi vào sổ cái, không cộng điểm và không là điều kiện của bước nào: bài đi thẳng từ writer tới QA tự động theo yêu cầu của chủ website ngày 23/10.

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

### Kiểm tra độc lập lần ba trên bảy bản đã gộp (23/10/2026)

Kết luận của reviewer: giữ cả bảy (mỗi bài dạy một phép tính, khung hay quy trình mà trang FAQ không dạy được; không cần gộp hay giữ thêm). Số liệu được tính lại bằng script và bằng tay.
Phát hiện: 1 lỗi chặn ở TH-VI-0019 (câu "chênh lệch chỉ xuất hiện nếu bạn trả xe sớm hơn" sai: chỉ cần số ngày thực tế lệch kế hoạch là hai cách tính khác nhau; kèm một ngưỡng "quá hai tuần" mâu thuẫn với chính ví dụ
mười ngày), 16 chỗ cần sửa (đường nối sau khi gộp, "thường được hiểu", khẳng định về cách cửa hàng xử lý trả sau 21:00, câu phạm vi của TH-VI-0016, từ khóa vắng trong meta của TH-VI-0011, ảnh nhận xe chưa được dặn ở TH-VI-0058...)
và 27 chỗ nhỏ. Đã sửa tất cả lỗi chặn và chỗ cần sửa rồi nộp lại sáu bản (TH-VI-0004 sạch, giữ nguyên); precheck của cả bảy: không lỗi nội dung.

Còn lại, nói thẳng (reviewer ghi nhận, chưa giải quyết bằng viết lại): (a) cả bảy bài cùng kết thúc bằng một đoạn liên hệ giống nhau và năm bài mở đầu bằng cùng một công thức "áp dụng cho chuyến của bạn cần được xác nhận khi đặt xe";
(b) giọng trung lập kiểu hướng dẫn người tiêu dùng vẫn nằm trên trang của cửa hàng; (c) năm bài chỉ đưa câu hỏi chứ không đưa đáp án vì cửa hàng chưa trả lời. Cả ba cần quyết định hoặc dữ kiện của chủ cửa hàng
([OWNER-QUESTIONS.md](OWNER-QUESTIONS.md)); không có bài nào nên xuất bản trước khi chủ cửa hàng xem giọng văn.

## Lô VI #3 (23/10/2026, lần 5): mười bốn bản mới từ chủ đề `editorial_only`

Chọn từ các dòng matrix chỉ cần `editorial_only` (cộng `first_party_facts`) mà ý định không phụ thuộc vào chính sách chưa xác nhận (giao xe, quy trình cọc, hoàn cọc): kỹ năng lái, quần áo, đi nhóm, lập kế hoạch ngày, xe số/xe côn/xe ga, chi phí đi hai người.
Nhập bằng `intake` với bằng chứng first-party **mới** (chụp lại sau khi chủ website xác nhận phí gia hạn 20.000 đồng một giờ, quá 6 giờ tính một ngày thuê), viết bằng `pack`/`build`, kiểm bằng `precheck` rồi nộp `--waiting-for auto`:
TH-VI-0018, 0022, 0134, 0146, 0151, 0158, 0267, 0268, 0359, 0371, 0459, 0484, 0487, 0491. Tất cả `WAITING_DATA` (`FEATURED_MEDIA`, `INTERNAL_LINKS`), điểm hiện tại 62,5/80, điểm tiềm năng 100 khi có dữ liệu, không lỗi nội dung.

### Rà soát độc lập trước khi nộp (23/10/2026)

Một tác tử khác (chỉ đọc) đọc cả mười bốn bản, tính lại mọi phép toán, tìm từ bị cấm bằng chính regex của QA và so chồng lấn. Số liệu **đúng** (0018, 0022, 0484, 0487 tính lại không sai), **không có** từ về giấy phép/luật/mức phạt/cọc/hoàn tiền. Nó tìm ra những điều tôi đã sửa trước khi nộp (khoảng 80 chỗ):

- **Một lỗi chặn về an toàn (TH-VI-0371):** câu "chấp nhận rằng xe sẽ đi ra ngoài đường cua một chút" trên đường hẹp có xe tải; đã viết lại (vào cua đủ chậm để xe trôi ra vẫn nằm trong làn; ở cua phải phía ngoài cua là làn ngược chiều, ở cua trái là mép đường có cát) và thêm lời dặn dừng gọi cửa hàng nếu tay lái rung hoặc phanh lạ.
- **Câu ngầm cho rằng cửa hàng có dịch vụ chưa xác nhận:** thử xe trước khi nhận, đổi sang xe số, hai người cùng lái, trả muộn được chấp nhận, hướng dẫn dọc đường, kèm áo mưa. Tất cả đã đổi thành câu hỏi cho cửa hàng hoặc bị bỏ.
- **Mâu thuẫn giữa các bài và với chính nó:** dép lê "chỉ dùng cho xe ga" (mâu thuẫn bốn bài khuyên giày kín mũi), thứ tự chạy nhóm (0459 và 0484 khác nhau), cách phá thế hòa nêu hai lần với hai quy tắc khác nhau ở 0484, lời dặn xe số/xe côn lẫn nhau (phanh sau là bàn đạp chân phải trên xe số, cần tay trái trên xe ga), ví dụ khung giờ ở 0487 (đệm 1,5 giờ không khớp quy tắc một phần năm; đã tính lại thành 9 giờ, đệm 2 giờ, còn 7 giờ).
- **Chồng lấn đoạn văn** (0151 với 0359, 0134 với 0158, 0146 với 0268): đã chia lại phần của từng bài.
- **Cảm giác sản xuất hàng loạt:** 12/14 kết đoạn mở đầu bằng cùng một câu lộ trình "Bài này …", 11/14 kết bằng cùng một câu trỏ vào chuyên mục, 6/14 có cùng đoạn địa chỉ, mỗi bài một bảng ba cột. Sau sửa: 2/14 còn câu lộ trình ở đoạn mở đầu, câu kết đổi theo ngữ cảnh, đoạn địa chỉ chỉ còn ở hai bài cần nó (0484, 0491), số bảng từ 1 đến 3 theo nội dung.

**Còn lại, nói thẳng:** (1) cả mười bốn bài chỉ liên kết tới chuyên mục VI đang có và tới bài cùng lô (chưa sống), nên QA cần ít nhất một liên kết tới trang/bài nội dung VI đang sống
(`minimum_internal_content_links = 1`); 11 trang tĩnh VI đã tồn tại nhưng slug chưa nằm trong repo. Cách giải: khi audit có thẩm quyền liệt kê các trang ấy, `claim --revise` từng bản để thêm liên kết dịch vụ theo `internal_link_plan` của dòng ma trận;
mỗi bài có liên kết sống riêng nên không còn phụ thuộc chéo giữa các bản thảo. (2) Ảnh có alt tiếng Việt chưa tồn tại. (3) Chưa có inventory từ adapter.

## Lô EN #1 (23/10/2026, lần 5): bảy bản mới

TH-EN-0005 (gọi xe hay thuê xe cả tuần), 0012 (nhận xe ngày đến hay ngày thứ hai), 0065 (xe số/xe côn tay/xe ga), 0125 (giải thích sự cố không biết tiếng Việt), 0139 (lâu không lái), 0140 (đi nhóm), 0141 (khoảng cách an toàn).
Cùng cách làm: `intake`, `build`, `precheck`, `submit --waiting-for auto` (`WAITING_DATA`). Từ container này không truy cập được `rentbikehanoi.com`, nên liên kết chỉ trỏ tới bài EN đã có trong inventory và các chuyên mục.

Rà soát độc lập (chỉ đọc) cũng không thấy từ bị cấm và tính lại toàn bộ số liệu của TH-EN-0005 (đúng). Đã sửa trước khi nộp:
**TH-EN-0005** liên kết tới bài chưa đăng (chặn) và đếm sai số chặng; **TH-EN-0012** khẳng định chính sách ngoài giờ mở cửa mà cửa hàng chưa xác nhận;
**TH-EN-0065** một khẳng định sai về cần ga; **TH-EN-0139** ngưỡng "nhiều dấu hiệu mới hoãn" (một dấu hiệu là đủ) và lời trấn an quá mức; **TH-EN-0140** mâu thuẫn "xem vị trí khi đang chạy" với "không dùng điện thoại khi chạy", điểm hẹn ở mép lề/vỉa hè;
**TH-EN-0141** "đánh lái sang bên cạnh khi không phanh kịp" có thể là làn ngược chiều; **TH-EN-0125** "thay xe" như một quyền lợi. Mỗi bài được viết lại theo các điểm trên và bỏ đoạn liên hệ giống nhau ở cuối.

## Vòng liên kết giữa các bản thảo (23/10/2026, lần 5)

Tìm ra khi diễn tập "bài nào qua QA trước", không phải do reviewer: QA coi liên kết tới trang chưa sống là lỗi cứng (`INTERNAL_LINK_NOT_LIVE_VERIFIED`; trong một bản chờ dữ liệu thì thành chờ `INTERNAL_LINKS`) và cần ít nhất một liên kết nội dung sống.
Mười bốn bản của lô VI #3 chỉ trỏ tới chuyên mục và tới bản cùng lô, bốn nhóm bản trỏ vòng quanh nhau (ví dụ 0359↔0371; công cụ phát hiện vòng báo đúng bốn nhóm trước khi cắt). Dù sau này có trang dịch vụ VI sống thì những cặp ấy vẫn không bao giờ qua, vì bản nào cũng chờ bản kia đăng trước.

Đã làm: công cụ phát hiện (`writing.link_graph`; `next` có `planned_link_cycles`; `precheck`/`build` có `planned_links`, `link_cycle` và lint `LINT_LINK_CYCLE`/`LINT_PLANNED_LINK`, kiểm bằng test và đột biến); cắt chín liên kết ở tám bản VI đã lưu rồi nộp lại bằng `claim --revise`
(hoàn thiện, không phải sửa lại: `repair_count` vẫn 0) và sáu liên kết ở lô #4 trước khi nộp. Quy tắc: một bản chỉ trỏ tới bản viết trước nó, không bao giờ ngược lại; nhắc tới một bản chưa đăng thì ghi bằng chữ, không bằng liên kết. `next --language vi` báo `planned_link_cycles: []`.
Còn lại: các "gốc" của thứ tự này (0022, 0146, 0359...) chỉ trỏ chuyên mục, nên mỗi gốc vẫn cần một liên kết sống của riêng nó (trang dịch vụ VI) khi audit có thẩm quyền liệt kê chúng; không thể bịa slug.

## Lô VI #4 (23/10/2026, lần 5): mười bản về tiền thuê, chi phí và nhóm

TH-VI-0013 (khoản dự phòng), 0218 (kiểm tra xe khi gia hạn), 0003 (ngày hay tuần), 0026 (xe số hay xe ga cho một tuần), 0065 (thuê tháng hay thuê lẻ), 0140 (sinh viên, nhà trọ), 0197 (chia xăng khi dùng chung xe tháng), 0008 (chia tiền nhóm bạn), 0224 (nhật ký lỗi chập chờn), 0090 (người quen đi nhận xe).
Mỗi bài dùng phép tính từ khoảng giá tham khảo đã xác nhận (điểm hòa vốn ngày/tuần/tháng, chia theo km, quỹ chung...) và có khung riêng. Tất cả `WAITING_DATA` (`FEATURED_MEDIA`, `INTERNAL_LINKS`), `repair_count` 0, không lỗi nội dung.

Rà soát độc lập (chỉ đọc; tính lại mọi phép toán, chạy regex REGULATED/FIRSTHAND của QA lên từng bài). Sai số học duy nhất: TH-VI-0065 ("bốn tuần rưỡi" nhưng nhân với 4,3; "8 ngày" mâu thuẫn "9 ngày"). Các lỗi chặn và chỗ cần sửa đã áp dụng:

- **Chính sách cửa hàng bị ngầm khẳng định:** 0013 "tính tròn từng giờ" (mâu thuẫn đoạn sau của chính nó; phần lẻ của giờ chưa xác nhận), 0090 mũ bảo hiểm như món cửa hàng có sẵn; mềm hơn ở 0065 (cách tính theo ngày, không giao nhận), 0197 (hai người cùng lái), 0140 (thử xe), 0224 (cổng sạc), 0218 (kênh nhắn tin).
- **An toàn (0224):** nhật ký bị gọi là "lỗi nhẹ" trong khi bảng ghi "máy tắt giữa đường" và đèn nháy; thiếu quy tắc dừng xe khi chết máy giữa dòng xe hoặc đèn hậu/phanh/xi nhan không sáng ban đêm; "đề liên tục" sau khi lội nước; "ghi ngay" có thể bị hiểu là ghi lúc đang lái; "sáng sớm" trái giờ mở cửa 09:00.
  Đã đưa phần dừng xe lên đầu bài với số điện thoại và giờ mở cửa đã xác nhận, bỏ giả định kênh nhắn tin.
- **Chồng lấn nội dung (QA không bắt được, độ chồng chữ cao nhất 0,104):** danh sách kiểm tra 0218 và 0090 (0090 chỉ giữ bốn điều chỉ người thứ hai làm được, nối tới 0218), khung quyết định 0026 và 0140, ba cách chia 0008 và 0197, "rút sát ngày" ở 0008 và 0484.
- **Lặp khuôn:** đoạn "Nối tiếp từ đây" ở 8/10 bài, câu phí gia hạn ở 6/10, "Ví dụ với số giả định" ở 5/10, câu rào giá ở 7/10, khung tin nhắn […] ở ba bài. Sau sửa: không bài nào còn "Nối tiếp từ đây", câu phí gia hạn chỉ ở 0013 và 0218 (nơi nó là chủ đề), khung tin nhắn […] chỉ ở 0218.

Còn lại: các số xăng/giá trong ví dụ là số tự đặt (giá xăng hiện hành chưa kiểm được ngoài repo); mọi bài vẫn chờ ảnh có alt tiếng Việt và liên kết sống (xem mục vòng liên kết).

## Lô VI #5 và EN #2 (23/10/2026, lần 5): bốn bản VI và ba bản EN

TH-VI-0128 (thuê xe ga một tuần để thử), 0121 (nhóm nhiều xe cùng loại xe ga), 0263 (áo phản quang buổi tối ngoại thành), 0445 (ăn no rồi lái xe); TH-EN-0001 (ngày hay tuần, sáu ngày), 0002 (hai ba tuần: tuần hay tháng), 0009 (chỉ cuối tuần: thuê lẻ hay thuê tháng).
Cùng cách làm, cùng rà soát độc lập (chỉ đọc). Đã sửa các lỗi chặn trước khi nộp:

- **Nội dung sức khỏe/an toàn không có nguồn (0445):** lời khuyên ăn uống kèm tác dụng sinh lý, "trạng thái tỉnh hơn", lời dặn gọi xe cho đoạn về mà không nhắc chiếc xe thuê, "đừng tự đổi người lái" không có ngoại lệ an toàn. **0128:** "gặp mưa đừng né, thử phanh" với người có thể mới lái. Tất cả đã viết lại.
- **Khẳng định số liệu không đỡ được:** TH-EN-0001 mở bài nói sáu ngày là lúc hai giá "sát nhau nhất" (bảng của chính nó cho thấy sát nhất ở 4–5 ngày) và meta nói "scooter" trong khi mọi số là xe số; TH-EN-0002 "một khối tuần thứ hai đã đắt hơn cả tháng" (sai: cần hai khối), "hai khoảng chồng lên nhau rộng" (không đúng);
  TH-EN-0009 "tối đa bốn chuyến bằng xe buýt" (đúng là tám đến mười), "mỗi lần thuê ngắn là hai chuyến tới cửa hàng" (giao xe chưa xác nhận), "trả xe muộn nhất 21:00 chủ nhật" (chính sách chưa xác nhận), "cho phép kết hợp" (chưa xác nhận).
- **Chính sách cửa hàng bị ngầm khẳng định:** TH-VI-0263 mũ là đồ thuê; TH-EN-0001 không hoàn tiền/linh hoạt như dữ kiện; TH-VI-0445 trả muộn bị đồng nhất với gia hạn.
- Bốn bản VI và ba bản EN sau sửa: không lỗi nội dung, `WAITING_DATA`, `repair_count` 0. TH-EN-0001 nay nêu cả xe ga (khai báo thêm giá ngày/tuần xe ga), TH-EN-0009 có đoạn nói rõ thuê tuần chỉ để đi hai ngày không có lợi.

Còn lại, nói thẳng: TH-EN-0001 trùng phương pháp với TH-VI-0003 và TH-EN-0002 chia một câu tính toán với TH-VI-0065 (cùng một quyết định của người thuê, hai thị trường đọc; đã đổi cách diễn đạt và thứ tự câu hỏi, không phải bản dịch, và không có cặp hreflang nào được lên kế hoạch);
TH-EN-0001 và TH-EN-0009 cùng một "động cơ" tính toán nên không nên đăng liền nhau. Từ khóa chính tiếng Anh của ba bài EN là cụm của ma trận nên không xuất hiện nguyên văn trong tiêu đề (chỉ là gợi ý lint, QA không kiểm).

## Mười bản EN hoàn tất bằng dữ liệu thật; khôi phục sổ cái phiên (23/10/2026, lần 5)

Sau khi chủ website merge PR #3, job `queue` làm mới inventory công khai: thư viện có ảnh với alt tiếng Anh và các bài EN đang sống. Hai thứ làm cho các bản EN từng phải chờ trở thành **lỗi nội dung** thay vì "chờ dữ liệu":
`submit --waiting-for FEATURED_MEDIA` bị từ chối (`FEATURED_MEDIA_OR_ALT_NOT_VERIFIED`: đã có ảnh, người viết phải chọn một ảnh trong danh sách của `pack`, không đặt ID), và `INTERNAL_LINKS` được xác minh.
Mười bản EN (TH-EN-0139, 0140, 0141, 0065, 0005, 0125, 0012 của lô #1 và 0001, 0002, 0009 của lô #2) được hoàn tất bằng ảnh có sẵn (ID 662 "Motorbike rental in Hanoi with a scooter on a Hanoi street" và ID 76 "Motorbike rental in Hanoi with scooters and motorcycles"),
`precheck` 100/100 không hard fail, rồi `submit`: QA tự động chạy ngay và cho **PASS 100/100 (80/80 điểm thô), `repair_count` 0** cho cả mười. Chín bản EN của V5 (cũng dùng ID 662 cho bảy bản) đã PASS ở job `queue` lúc 13:24 UTC.
Nói thẳng: QA này chạy trên inventory công khai (`public-rest-unverified`, chụp 13:23 UTC), đạt không có nghĩa là đã đăng (release vẫn OFF) và job `queue` sẽ QA lại khi sổ cái được chuyển.

Cùng lúc, sổ cái phiên bị lệch (53 sự kiện chưa chuyển so với 10 sự kiện chuyển giao và QA của sổ cái chung). Đã khôi phục bằng `sync --apply --discard-unpromoted`: 22 bản VI (8 bản sửa, 10 + 4 bản mới) được nộp lại từ chính tài liệu đã lưu, cùng địa chỉ bài, không tốn lượt sửa;
ba bản EN của lô #2 không còn nộp lại được như bản chờ (xem trên) nên được hoàn tất kèm ảnh, và bảy bản EN của lô #1 cũng vậy, nên mười bản EN có địa chỉ bài mới (các bản chờ cũ vẫn còn trong tài liệu và lịch sử).

## Lô EN #3, viết lại liên kết 35 bản VI và bàn giao vòng 2 (23/10/2026, lần 6)

**Lô EN #3 (8 bài, TH-EN-0045, 0007, 0010, 0039, 0040, 0032, 0126, 0037).** Chọn từ ma trận vì chỉ cần dữ kiện của cửa hàng; mỗi bài có ảnh có sẵn (ID 662 hoặc 76), liên kết tới bài EN đang sống và tới chuyên mục. Rà soát độc lập chỉ đọc (đọc thân bài, meta, dòng ma trận, tệp dữ kiện cửa hàng và `quality.py`, tính lại mọi bảng) trả 12 điểm chặn và 30 điểm sửa; tất cả đã kiểm chứng rồi áp dụng:

- *Chính sách cửa hàng bị khẳng định khi chưa xác nhận.* TH-EN-0045 nói "trả muộn tính theo phí gia hạn", "phí bị chặn trần bởi bảng" và "báo sớm thì rẻ": chủ cửa hàng chỉ xác nhận phí gia hạn 20.000 đồng một giờ, quá 6 giờ tính một ngày thuê, nên bài chỉ còn nói "nếu cửa hàng tính trả muộn như vậy" và hỏi cách tính; ví dụ 6 giờ rưỡi, vốn dựa vào quy tắc làm tròn chưa xác nhận, đổi thành 7 giờ.
  TH-EN-0032, 0126 và 0039 nói "ngoài giờ cửa hàng không giúp được/không ai trả lời": chỉ giờ mở cửa là đã xác nhận, nên bài nói "đừng trông chờ vào câu trả lời" và khuyên hỏi lúc đặt xe có ai liên hệ được ban đêm không. TH-EN-0126 bỏ câu "không thuộc quyền bạn duyệt thay chủ xe" (một quy định không có nguồn).
- *Câu an toàn đọc ngược hoặc cho phép rủi ro.* TH-EN-0040 để "mọi hạng mục chưa đánh giá được" sang kiểm tra ban ngày hôm sau (phanh cũng là hạng mục): nay chỉ để lại vết xước thẩm mỹ, còn phanh, đèn, lốp, lái phải kiểm trước khi đi; phanh mềm thì dừng nơi an toàn rồi gọi, dắt bộ chứ không chạy. TH-EN-0039 "hạn chót là thứ đầu tiên bỏ, không phải giờ trả" đổi thành "bỏ điểm dừng đó trước; giờ trả là thứ không được dịch".
  Thêm dòng an toàn còn thiếu: chạy đêm có đèn và không vội (0039, 0040, 0032), đã uống rượu thì để xe lại (0032), không đọc hay trả lời tin nhắn khi lái (0045, 0037), không để xe hoặc chìa khóa cho người lạ khi cửa hàng đóng (0045, 0126, 0037).
- *Một cách đếm ngày thứ ba mà bài không minh họa* (TH-EN-0007): "ngày theo giờ mở cửa" được định nghĩa là ngày kết thúc lúc đóng cửa, cho cùng tổng với cột ngày lịch khi trả trong 09:00-21:00; lời khuyên "lên kế hoạch buổi sáng cuối thay vì buổi tối cuối" sai (20:00 ngày 2 và 11:00 ngày 3 cùng tốn hai ngày) nên đổi thành "trả trước giờ đã nhận xe".
- *Câu khẳng định tần suất không có nguồn* ("thường", "hiếm khi", "thường trung thực") được bỏ ở 0007, 0032, 0037, 0126; giọng "cửa hàng chưa công bố câu trả lời" (nghe lạ trên chính trang của cửa hàng) đổi thành "là việc của cửa hàng cho biết".
- *Trùng lặp ý định.* TH-EN-0126 gần nhất với bài hẹn dịch vụ đang sống và bài thủng lốp, nên thêm liên kết tới bài hẹn dịch vụ; TH-EN-0032 thêm liên kết tới bài khóa xe và bài hỏng xe sau 21:00; TH-EN-0037 thêm liên kết bài Google Maps cho địa chỉ ngõ khó tìm. Cụm cuối bài "chuyên mục này gom các bài khác" và các câu mở đầu "This guide shows..." được đổi cách diễn đạt để tám bài không cùng một khung.
- Cụm tiếng Việt trong TH-EN-0126 thành "Sửa hết bao nhiêu tiền ạ?" và "Cho tôi xem chỗ hỏng với" (tự nhiên hơn câu cũ); đây là phán đoán của người viết, chưa có người bản ngữ xác nhận.

Điểm QA tự động sau khi sửa: **100/100, không lỗi nội dung, 8/8 PASS** (lint còn lại chỉ là gợi ý: cụm từ khóa của ma trận không xuất hiện nguyên văn).

**Viết lại liên kết 35 bản VI.** Sau khi inventory của adapter cho thấy 11 trang VI đã đăng, mọi bản VI đã lưu chỉ liên kết tới chuyên mục và tới bài chị em chưa đăng. Với mỗi bản: bỏ liên kết tới bài chưa đăng, bỏ luôn những chỗ chỉ nhắc tên một bài chưa tồn tại (mười chỗ ở tám bản, một trong số đó nằm trong ô của bảng), viết lại câu thành lời khuyên tự đứng được, và thêm liên kết tới trang VI hợp nhất: bảng giá, xe ga, thủ tục, giao nhận, câu hỏi thường gặp hoặc liên hệ.
Tất cả 35 thay thế khớp đúng một chỗ khi áp dụng; QA tự động trên inventory của adapter: 87,5 mỗi bản, không lỗi nội dung, chỉ còn thiếu ảnh. Mười một bản `HELD` không đụng tới.

**Bàn giao vòng 2.** `sync --apply --discard-unpromoted` rồi `scripts/replay_unpromoted.py`: nhập lại 8 chủ đề, nộp lại 10 bản EN từ tài liệu đã lưu (10 PASS), nộp 35 bản VI mới (22 theo kế hoạch, 13 theo kế hoạch bổ sung vì sổ cái chung đã có phiên bản cũ của chúng), nộp lô #3. Kế hoạch `promote` ngoại tuyến với `factory-state` v448: FAST_FORWARD.

## Lô EN #4 và #5, VI #6 và #7 (23/10/2026, lần 7)

Mỗi lô: chọn từ `next` các dòng ma trận chỉ cần dữ kiện cửa hàng và đủ khác nhau về ý định → `intake` (`make_candidates`) → viết → `dry_build` → rà soát độc lập chỉ đọc → kiểm chứng và sửa → `claim --topic-id`, `build`, `submit --waiting-for auto` từng bản.

- **EN #4:** tiền tệ trong báo giá (0003), phụ kiện kèm xe (0006), cửa hàng không trả lời trước khi đến (0017), mất biên nhận hoặc ảnh nhận xe (0018), số điện thoại đưa cho cửa hàng (0023), mức xăng khi trả (0038), đặt xe tháng trước khi chuyển đến Hà Nội (0036), kết thúc kỳ thuê tháng (0031).
- **EN #5:** hư hại phát hiện sau khi rời cửa hàng (0020), hao mòn hay hư hỏng bị tính (0015), đặt trước hay đến thẳng (0021), ra nước ngoài giữa kỳ thuê tháng (0030), nhận xe ở ga, quán cà phê hoặc cổng nhà (0042), mức pin khi trả xe điện (0075), một xe cho đi làm và chuyến cuối tuần (0035), đặt qua nền tảng hay trực tiếp (0013).
- **VI #6:** kỳ thuê "một tháng" tính từ ngày nào (0064), gọi hay nhắn khi xe có sự cố (0248), tiệm ven đường mời thay phụ tùng (0246), xe điện thuê tháng pin yếu dần (0176), giá đã gồm những phụ kiện nào (0010), nhận và trả xe quanh giờ hành chính (0086), nhận xe lúc tối hoặc mưa bằng đèn điện thoại (0088), cách đọc giá ghi "từ" hoặc "liên hệ" (0017).
- **VI #7:** trầy xước nhẹ khi dắt xe vào ngõ (0250), tự ngã trên đường ướt (0251), thủng lốp giữa đường (0247), chở người ngồi sau chưa quen xe máy (0373), về quê một tuần giữa kỳ thuê tháng (0072), nhận xe chiều hôm trước để đi sớm (0087), kéo vali đến nhận xe (0100), đến đúng giờ hẹn nhưng xe chưa sẵn sàng (0105).

**Cách làm đã chứng minh có ích** (nên giữ cho các lô sau): brief cho người rà soát nêu luật chủ website bằng lời rõ (chỉ những dữ kiện trong `config/business-facts.json` là dữ kiện về cửa hàng; mọi thứ khác chỉ được "hỏi cửa hàng"), danh sách liên kết cho phép, các lớp lỗi cần tìm (a đến h) và định dạng "ID | mức | loại | trích nguyên văn | lý do | thay thế", kèm giới hạn số lần gọi công cụ; người rà soát không được sửa tệp; mọi phát hiện được tôi kiểm chứng (khớp đúng một chỗ) rồi áp dụng bằng script có assert. Một nhận xét của người rà soát về "từ miền Nam" (kẹt xe) và một về cách lên xe được kiểm bằng lập luận, không chép nguyên.

**Lỗi lặp lại cần canh khi viết** (rà soát tìm ra ở cả bốn lô): khẳng định tần suất ("thường", "nhiều người", "hầu hết"); thời lượng và con số bịa, kể cả "mười phút", "nửa giờ", mốc giờ không ghi "gợi ý" hay "ví dụ"; câu ngầm hiểu cửa hàng có hồ sơ, biên nhận, tạm dừng thuê, cọc từng lần thuê, giao nhận ngoài cửa hàng; an toàn trấn an vô điều kiện hoặc thứ tự sai (sơ cứu, sạc pin nóng, mùi xăng, đọc điện thoại khi lái); mô tả liên kết nói nhiều hơn tiêu đề trang đích; cùng một đoạn kết và câu mở đầu "This guide ..." ở nhiều bài. Bản EN đã `READY` không sửa lại được bằng `claim --revise`, nên phải rà soát trước khi nộp.
