# Hướng dẫn soạn seed cho matrix VI500 và EN500

Tài liệu này dành cho người (hoặc phiên AI) viết các dòng ý tưởng bài trong
`data/bilingual/seeds/`. Seed **không phải bài viết** và không phải bằng chứng
nghiên cứu: nó là một dòng kế hoạch gồm tiêu đề dự kiến, từ khóa, ý định tìm kiếm
và yêu cầu nguồn. Generator `scripts/build_matrices.py` ghép seed với ID, parent
và URL thật trong `data/bilingual/live-categories-2026-10-22.json`.

## Định dạng

Mỗi dòng là một JSON, một dòng một chủ đề, trong file `data/bilingual/seeds/vi-<nhóm>.jsonl`
hoặc `en-<nhóm>.jsonl`:

```json
{"c":152,"t":"Tiêu đề dự kiến","k":"từ khóa chính","q":"Câu mô tả nhu cầu cụ thể của người tìm kiếm","i":"commercial_investigation","s":"prices","r":["first_party_facts"],"p":1,"u":"slug-khong-dau"}
```

| Khóa | Ý nghĩa | Ràng buộc |
|---|---|---|
| `c` | ID category mục con (leaf) trong bảng bên dưới | Đúng ngôn ngữ, đúng nhóm được giao |
| `t` | Tiêu đề/H1 dự kiến, viết tự nhiên như người đọc bản ngữ | 25–120 ký tự; không có giá tiền, số tiền, "rẻ nhất", "tốt nhất", "đảm bảo", "miễn cọc" |
| `k` | Cụm tìm kiếm chính | 6–80 ký tự; không trùng cụm khác |
| `q` | Một câu mô tả **nhu cầu riêng** của chủ đề này (ai, đang ở tình huống nào, cần quyết định gì) | 40–400 ký tự; không lặp ý chủ đề khác |
| `i` | Loại ý định | `informational`, `commercial_investigation`, `comparison`, `transactional_support`, `troubleshooting`, `planning`, `local_navigation` |
| `s` | Trang dịch vụ để dẫn CTA/liên kết nội bộ | khóa trong `data/bilingual/service-targets.json` |
| `r` | Loại nguồn phải thu thập trước khi viết | một hay nhiều trong `first_party_facts`, `official_vn_law`, `official_weather`, `official_health`, `official_venue`, `official_transport`, `manufacturer_manual`, `field_check`, `editorial_only` |
| `p` | Ưu tiên viết | 1 = gần dịch vụ/hỗ trợ khách thuê, 2 = so sánh/hướng dẫn, 3 = khám phá/nội dung rộng |
| `u` | Slug | chỉ a–z, 0–9 và dấu gạch ngang, 8–90 ký tự, không dấu tiếng Việt, duy nhất toàn site và khác slug của 275 bài + 6 trang tĩnh + từ khóa hệ thống |

Slug tiếng Việt: bỏ dấu, `đ` thành `d`, ví dụ `dat-coc-xe-may-bang-cccd`. URL cuối cùng là
`https://rentbikehanoi.com/vi/<slug>/` (VI) hoặc `https://rentbikehanoi.com/<slug>/` (EN).

## Quy tắc biên tập (bị kiểm tra bằng máy hoặc bằng review)

1. **Bản địa, không dịch.** Chủ đề VI xuất phát từ mối quan tâm của người dùng Việt
   (CCCD, GPLX, đăng ký xe, xăng E5/RON95, giờ cao điểm, mưa nồm, đường cấm xe máy,
   gửi xe phố cổ, thuê dài hạn cho sinh viên/người đi làm). Chủ đề EN xuất phát từ
   khách quốc tế và người nước ngoài ở Hà Nội. Không lấy câu hỏi của ngôn ngữ kia
   rồi dịch sang.
2. **Mỗi chủ đề có ý định riêng.** Không viết cùng một câu hỏi bằng nhiều tiêu đề,
   không chỉ đổi quận/phường, tên mẫu xe, tên điểm đến hay số ngày. Máy sẽ chặn
   tiêu đề trùng sau khi thay tên quận/mẫu xe bằng ký hiệu chung.
3. **Không cạnh tranh với trang dịch vụ.** Không viết bài chỉ để nhắm "thuê xe máy
   Hà Nội", "thuê xe máy giá rẻ" hoặc biến thể gần đúng của trang chủ/trang giá.
   Không tạo doorway theo phường/quận. Bài khu vực phải có giá trị tuyến đường
   thật (đi từ đâu, qua đâu, gửi xe, đoạn đi bộ).
4. **Không bịa dữ kiện.** Tiêu đề và `q` không khẳng định giá, giờ mở cửa, quy định
   pháp luật, tồn kho, chính sách của cửa hàng (giao xe, hoàn cọc, phụ phí gia hạn
   chưa được xác nhận), trải nghiệm trực tiếp hay lời hứa. Chủ đề được phép hỏi
   "cần hỏi cửa hàng điều gì" nhưng không trả lời thay cửa hàng. Chủ đề pháp lý
   phải có `official_vn_law`; thời tiết `official_weather`; sức khỏe (ví dụ mang thai, chấn thương) `official_health`
   và bài chỉ hướng người đọc hỏi chuyên gia y tế; địa điểm `official_venue`.
5. **Không trùng 275 bài tiếng Anh đang chạy** (xem
   `data/bilingual/live-posts-2026-10-22.json`) và 2 chủ đề đã vào hàng đợi
   (`data/bilingual/existing-queued-en.json`). Bài EN cũ dày ở: bảng giá/đặt cọc/bàn giao,
   kiểm tra xe, mũ bảo hiểm, nhiên liệu, đỗ xe, mưa/ngập, sự cố, 28 điểm tham quan
   và món ăn Hà Nội, hầu hết điểm đi trong ngày. Hãy tìm góc **chưa có**.
6. **Tránh phân mảnh vô nghĩa.** Mỗi mục con chỉ nên có số chủ đề mà bạn tự tin là
   khác nhau về ý định. Nếu không thể đủ số gợi ý mà vẫn khác nhau, viết ít hơn và
   nói rõ; không nhồi paraphrase. Sai lệch tối đa 20% so với bảng gợi ý.
7. **Trùng ý định giữa hai mục cũng là trùng.** Máy chỉ đo trùng từ. Cùng một tình huống người đọc (chăm người nhà ở bệnh viện,
   thẻ xe tháng ở chung cư, chở trẻ nhỏ, bảo hiểm trách nhiệm, trang phục chống rét) không được xuất hiện ở hai mục dù từ ngữ khác
   nhau. Trước khi thêm dòng hãy hỏi: người tìm kiếm có thỏa mãn khi đọc một dòng đã có không? Có thì bỏ.
8. **Không kiểm chứng nhu cầu tìm kiếm.** Không ghi lượng tìm kiếm hay thứ hạng.
   Matrix ghi `demand_evidence: NOT_MEASURED`.

## Chạy kiểm tra

```
PYTHONPATH=src python3 -m thuha.matrix check data/bilingual/seeds/vi-a.jsonl --language vi --categories 152,153,154,155
```

Lặp lại cho đến khi `problems` rỗng. Lệnh kiểm tra định dạng, ngôn ngữ, slug, trùng
lặp, mẫu doorway, quá giống bài EN cũ và phạm vi category. Tổng số bài đúng 500
VI / 225 EN mới được kiểm ở bước `python3 -m thuha.matrix validate` sau khi gộp.

## Mục con VI (tổng gợi ý 500)

| ID | Nhóm cha → mục | Số bài gợi ý | Phạm vi theo mô tả WordPress |
|---|---|---|---|
| 152 | Hướng dẫn thuê xe → Giá thuê và chi phí | 30 | Cách tính ngân sách thuê xe, khoản cọc và chi phí chuyến đi; xác nhận báo giá trước khi đặt. |
| 153 | Hướng dẫn thuê xe → Thủ tục và đặt cọc | 30 | Chuẩn bị giấy tờ, kiểm tra hợp đồng và hỏi rõ điều kiện đặt cọc khi thuê xe. |
| 154 | Hướng dẫn thuê xe → Thuê xe dài hạn | 25 | Kinh nghiệm thuê xe theo tuần hoặc tháng cho công việc và thời gian lưu trú tại Hà Nội. |
| 155 | Hướng dẫn thuê xe → Giao nhận và trả xe | 25 | Lên kế hoạch nhận xe, kiểm tra tình trạng xe, thống nhất địa điểm và thời gian trả. |
| 156 | Chọn xe và so sánh → Xe ga | 30 | So sánh xe ga theo vóc dáng, nhu cầu sử dụng và thông số đã kiểm chứng. |
| 157 | Chọn xe và so sánh → Xe số và xe côn | 30 | Tìm hiểu xe số, xe côn tay và cách lựa chọn theo kinh nghiệm lái xe. |
| 158 | Chọn xe và so sánh → Xe điện và xe 50cc | 20 | Tìm hiểu điều kiện sử dụng, giới hạn và thông số của xe điện, xe dung tích nhỏ; không mặc định cửa hàng có sẵn. |
| 159 | Sử dụng và chăm sóc xe → Nhiên liệu và tiêu hao | 25 | Đổ xăng, theo dõi mức tiêu hao và dự tính chi phí vận hành xe thuê. |
| 160 | Sử dụng và chăm sóc xe → Bảo dưỡng xe thuê | 25 | Kiểm tra trước chuyến đi, nhận biết dấu hiệu bất thường và trao đổi với cửa hàng trước khi sửa chữa. |
| 161 | Sử dụng và chăm sóc xe → Xử lý sự cố | 25 | Dừng xe an toàn, ghi nhận tình trạng và liên hệ cửa hàng khi xe gặp vấn đề. |
| 162 | Sử dụng và chăm sóc xe → Hành lý và phụ kiện | 25 | Sắp xếp hành lý, trang bị cá nhân và dụng cụ chỉ đường phù hợp khi đi xe máy. |
| 163 | Lái xe an toàn → Giấy phép và quy định | 30 | Tra cứu điều kiện giấy phép, quy định giao thông và nguồn văn bản hiện hành. |
| 164 | Lái xe an toàn → Giao thông và đỗ xe | 30 | Chuẩn bị lộ trình, quan sát giao thông và kiểm tra nơi đỗ xe hợp lệ tại Hà Nội. |
| 165 | Lái xe an toàn → Thời tiết và kỹ năng | 30 | Điều chỉnh kế hoạch theo mưa, nắng và khả năng lái; cân nhắc phương án di chuyển khác khi cần. |
| 166 | Khám phá Hà Nội → Khu vực và tuyến đi | 25 | Gợi ý tuyến đi theo khu vực cùng thông tin tiếp cận, gửi xe và đoạn đi bộ. |
| 167 | Khám phá Hà Nội → Điểm đến văn hóa | 25 | Tìm hiểu điểm đến văn hóa với nguồn thông tin, giờ mở cửa và điều kiện tham quan cần kiểm tra. |
| 168 | Khám phá Hà Nội → Ẩm thực và trải nghiệm | 25 | Lên lịch dừng chân ăn uống và trải nghiệm Hà Nội gắn với hành trình thực tế. |
| 169 | Hành trình từ Hà Nội → Đi chơi trong ngày | 15 | Lịch trình đi về trong ngày từ Hà Nội với quãng đường, điểm nghỉ và phương án dự phòng. |
| 170 | Hành trình từ Hà Nội → Chuyến đi cuối tuần | 15 | Chuẩn bị chuyến đi có lưu trú với hành trình vừa sức và kiểm tra điều kiện đường. |
| 171 | Hành trình từ Hà Nội → Lập kế hoạch chuyến đi | 15 | Chuẩn bị ngân sách, thời gian, hành lý, bản đồ và phương án di chuyển cho chuyến đi. |

## Mục con EN cần bù (tổng gợi ý 225; 275 bài hiện có được bảo vệ, không viết lại)

| ID | Nhóm cha → mục | Số bài gợi ý | Phạm vi theo mô tả WordPress |
|---|---|---|---|
| 123 | Motorbike Rental Guides → Rental Prices & Budgets | 15 | Compare rental periods, deposits and trip budgets; verify current quotations before booking. |
| 124 | Motorbike Rental Guides → Booking, Deposits & Handover | 15 | Documents, booking questions, deposits, vehicle inspection and return checklists for Hanoi rentals. |
| 125 | Motorbike Rental Guides → Weekly & Monthly Rentals | 15 | Planning longer rentals for work and stays in Hanoi, including maintenance arrangements and contract questions. |
| 126 | Motorbike Rental Guides → Delivery & Return Planning | 10 | Plan vehicle collection, permitted delivery locations and return times with the rental shop. |
| 141 | Motorbike Reviews & Comparisons → Automatic Scooters | 20 | Model comparisons, fit and everyday use of automatic scooters. |
| 142 | Motorbike Reviews & Comparisons → Manual & Semi-Automatic Motorbikes | 15 | Compare manual and semi-automatic options using verified specifications and rider needs. |
| 143 | Motorbike Reviews & Comparisons → Electric & 50cc Options | 10 | Eligibility, limitations and practical checks for electric and small-capacity vehicles; do not assume stock. |
| 129 | Bike Setup & Everyday Use → Fuel & Running Costs | 10 | Fuel choices, refuelling and practical running-cost calculations for rented motorbikes. |
| 130 | Bike Setup & Everyday Use → Rental Bike Maintenance | 15 | Pre-ride checks and maintenance questions for rental riders; contact the shop before repairs. |
| 131 | Bike Setup & Everyday Use → Luggage, Equipment & Navigation | 10 | Plan luggage, riding equipment and navigation for Hanoi journeys. |
| 132 | Parking, Weather & Breakdowns → Parking in Hanoi | 10 | Parking access, walking connections and location-specific checks for Hanoi visitors. |
| 133 | Parking, Weather & Breakdowns → Weather & Seasonal Riding | 10 | Prepare routes and equipment for seasonal conditions, rain and heat. |
| 134 | Parking, Weather & Breakdowns → Breakdowns & Roadside Help | 10 | Safe stopping, contacting the rental shop and explaining a vehicle problem. |
| 144 | Road Rules & Riding Safety → Licences & Legal Eligibility | 15 | Source-checked licence recognition, eligibility and legal questions for visitors to Vietnam. |
| 145 | Road Rules & Riding Safety → Riding Skills & Safety Planning | 10 | Pre-ride decisions, safety equipment, road awareness and transport alternatives. |
| 135 | Hanoi Routes & Sightseeing → Hanoi Neighborhoods & Routes | 10 | Useful neighborhood routes, access checks, parking and walking stops in Hanoi. |
| 136 | Hanoi Routes & Sightseeing → Food & Cultural Stops | 5 | Plan food and cultural stops with practical route and visitor information. |
| 137 | Day Trips from Hanoi → One-Day Motorbike Itineraries | 10 | Realistic day trips from Hanoi with route checks, rest stops and alternatives. |
| 138 | Day Trips from Hanoi → Weekend Trips & Overnight Routes | 5 | Prepare overnight journeys from Hanoi with realistic distances and eligibility checks. |
| 139 | Travel Guide → Trip Planning & Practicalities | 5 | Plan timing, budgets, navigation and transport alternatives for a Hanoi stay. |
