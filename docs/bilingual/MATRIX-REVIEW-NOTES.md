# Ghi chú review ma trận: chỗ cần người đọc ý định

Ma trận được kiểm bằng máy (`python3 -m thuha.matrix validate`): trùng ID/slug/URL/từ khóa, mẫu
doorway (đổi quận/mẫu xe), quá giống bài EN đang chạy, giá/lời hứa trong tiêu đề, sai ngôn ngữ,
sai category, số lượng. Kiểm tra đó dựa trên **độ trùng từ**, không phải hiểu nghĩa. Danh sách dưới
đây là những cặp **gần nhau về chủ đề** mà các tác giả seed tự báo; chúng khác nhau về tình huống và
quyết định của người đọc nhưng cần reviewer độc lập xác nhận trước khi `intake`
(`intent_review.verdict = DISTINCT`). Nếu reviewer thấy trùng, **gộp hoặc bỏ dòng seed**, đừng viết
hai bài. Số liệu nhu cầu tìm kiếm chưa đo (`demand_evidence: NOT_MEASURED`).

## EN mới so với bài EN đang chạy

- Giá/đặt cọc/bàn giao (123–126) gần các bài 1895, 1897, 1899, 1901, 1903, 1915, 1923, 1937, 3274,
  3280, 3300, 3305, 3405 (đặt cọc, ảnh hư hại, biên nhận, so báo giá, chuyến bay muộn, giao nhận,
  đổi xe, hợp đồng). Dòng gần nhất: "contract transfer", "substitute bike", "ending a monthly rental",
  "flight before the shop opens", "getting to the shop".
- Xe/nhiên liệu/bảo dưỡng (129–131, 141–143) gần 1943, 1945, 1947, 1954, 1956, 1977, 2006, 519, 3284 và
  ba bài 50cc. Dòng gần nhất: "spec sheet", "passenger", "neutral or first gear", "removable battery",
  "rated power plate", "fuel grade/pump payment".
- Giấy phép (144) gần 380, 461 và các bài IDP/50cc: "car licence only", "a shop says no licence needed".
- Điểm đi cuối tuần (138) "Mai Chau" nằm trong tỉnh Hòa Bình, gần bài Hòa Bình hai ngày (2072).
- Đỗ xe (132) và tuyến phố cổ (135) gần nhau nhưng khác ý định (gửi xe vs ra khỏi phố cổ theo đường một chiều).
- Thực thể (Tam Chuc, Kieu Ky, Pho Hien, Ecopark, Perfume Pagoda) chưa kiểm chứng: dòng nào cũng cần
  `official_venue` hoặc `field_check` trước khi viết.

Các cặp trùng thật giữa hai tác giả đã được validator phát hiện và xử lý: "hết xăng giữa đường" (EN 129 và 134;
giữ 134, thay 129 bằng "mức xăng khi bàn giao"); "làm nóng máy buổi sáng" (VI 156/159 và 160; giữ bản xe ga, thay bản 160 bằng "để xe
nằm yên khi đi công tác"); "vùng phát thải thấp" (VI 163 và 164; giữ 163, thay 164 bằng "nhường xe ưu tiên").

## VI mới

- 156–159: đồng hồ xăng/nạp xăng/chi phí xăng gần các bài EN 1947, 1956, 1958; sạc xe điện gần 1977, 3299,
  3350; độ tuổi 50cc gần ba bài 50cc; smart key gần 1925. VI viết cho người đọc Việt (E5/RON95, CCCD, tin nhắn
  hỏi cửa hàng) nhưng cùng chủ đề với bài EN thì reviewer cần xác nhận không phải bản dịch ý.
- 160–163: xe chết máy khi mưa/ngập, thủng lốp, đèn tắt buổi tối, chìa gãy gần 1989, 2003, 2008, 1925; GPLX
  cho Việt kiều gần bài IDP/đổi bằng; bảo hiểm trách nhiệm dân sự gần bài bảo hiểm du lịch 2015.
- 168–171: "làng nghề có đón khách" gần 3259, 3363, 2068; "ăn no buồn ngủ" gần 2019; chợ hoa Tết và
  qua đêm gần các bài Tết/gửi xe qua đêm; "Mộc Châu tự chạy hay xe khách" cùng kiểu 2074, 2078, 2080.
- 164–167: hét giá gửi xe, điểm trông giữ có phép, để xe trong ngõ họ hàng gần các bài EN về vé gửi xe và gửi xe
  qua đêm; đường rào chắn thi công/đường trên cao gần "Google Maps closed road" và "expressways"; giông lốc/gửi xe thuê khi
  thời tiết xấu gần các bài EN về mưa và cảnh báo giông; nồm ẩm gần bài vạch sơn/nắp cống trơn; cầu Long Biên, bến xe
  Gia Lâm, chợ đầu mối gần bài qua sông Gia Lâm, ngõ 5 Nguyễn Văn Cừ, chợ hoa Quảng Bá; Thăng Long tứ trấn, xin chữ đầu năm,
  ca trù cạnh các bài EN về đền Bạch Mã, đền Voi Phục, thư pháp, đàn bầu. Hồ Tây xuất hiện ở 4 dòng của 166 (ngắm sen,
  hoa sữa... cùng khuôn): reviewer cân nhắc gộp để tránh doorway theo địa điểm.
- Giữa các category VI: đổ xăng khi nhận/trả (159 với 155); xe không cốp (157 với 162); hạng bằng xe côn
  (157 với 163); xe điện đi mưa (158 với 165); nhóm nhiều xe (168, 169, 171); trời rét (168, 170); rượu bia
  (168, 170); giờ trả xe (168, 170).

## Quy tắc xử lý

1. Reviewer đọc `search_intent` của hai dòng, không chỉ tiêu đề.
2. Khác nhau thật: ghi `DISTINCT` kèm lý do vào `intent_review`.
3. Trùng: bỏ dòng ít giá trị hơn khỏi seed, chạy `python3 scripts/build_matrices.py`
   (cân lại 500/225 bằng chủ đề mới thật sự khác, không paraphrase).
4. Chủ đề pháp lý, thời tiết, địa điểm: không viết khi chưa chụp nguồn chính thức còn hiệu lực (`NEEDS_SOURCE`).
