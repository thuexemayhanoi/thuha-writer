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

- 152–155: "trả sớm", "trả muộn", "chuyển gói ngày sang tuần", "xe hỏng mất ngày" gần các bài EN về gia hạn và đổi xe
  (252, 1923) nhưng khác ở góc tính tiền; 153: hóa đơn công tác phí (EN 3324), giữ căn cước gốc (EN 1931), giấy tờ xe khi
  bị kiểm tra (EN 3289), Việt kiều (EN 3287, 3288), mất xe (EN 1927); 153 với 163 chồng nhau ở bằng lái, độ tuổi, bảo hiểm;
  155: nhận xe ở bến Gia Lâm và từ phố cổ sang Long Biên gần EN 1937, 3405; 153 (hoàn cọc) với 155 (cuối kỳ thuê tháng); 152
  (trả sớm) với 154 (chấm dứt sớm hợp đồng tháng); 155 (mức xăng) với 159. - EN thay thế (en-d): "exhaust smoke colour at start-up" (130) gần "smoke or a burning smell" (134: tắt máy, tránh xa, gọi cửa hàng) —
  ý định khác nhau (ghi nhận để mô tả vs dừng khẩn cấp) nhưng reviewer cần xác nhận; "where to stay when you plan to ride" (139) gần
  các bài đỗ xe khách sạn (EN 1981) và 132 apartment block; "which sights close on which days" (139) gần 139 "Do You Need the Bike
  Every Day?"; "Wave Alpha or Sirius" (142) gần 142 Exciter/Winner và 141 Vision/Air Blade; "house-hunting week" (125) gần 125 trial week
  và 123 "Count Your Trips First". Các cặp cần reviewer đọc `search_intent`.

Một cặp trùng thật A/D ("chỗ để xe ở nhà trọ khi
  thuê tháng", 154 và 164) đã được validator bắt và thay bằng chủ đề lùi xe khỏi chỗ đỗ chật.
- Chủ đề nhạy cảm về sức khỏe (VI 156 "đang mang thai có nên tự lái xe ga thuê"): nguồn bắt buộc `official_health`, bài chỉ
  hướng người đọc hỏi bác sĩ, không đưa lời khuyên y tế; reviewer cân nhắc có nên giữ.
- 156–160 (đợt bổ sung): 160 "chân chống cạnh lỏng" gần 157 "thử cần số/côn khi nhận xe" (cùng bước nhận xe, khác bộ phận);
  157 "đường ướt về số thấp quá gấp" gần 157 "xuống đèo phanh động cơ" và 165 "mưa phùn kéo dài"; 160 "việc nhỏ nào tự làm"
  gần hai bài EN 3303 và 3384.
- 161–165 (đợt bổ sung): 163 "cầm ô, xách đồ, buông một tay khi lái" và 163 "nhìn bản đồ, đeo tai nghe khi lái" cùng nhóm hành vi
  bị cấm khi lái, khác hành vi; 164 "biển cấm đỗ ngày chẵn/lẻ" và 164 "cấm dừng, cấm đỗ khác nhau" cùng chủ đề biển phụ; 164 "dông
  lốc: chỗ để xe qua đêm" và 165 "giông lốc giữa đường" (xe đã đỗ so với xe đang chạy); 165 "mặt đường trơn lá, bùn, dầu loang"
  gần bài EN về vạch sơn và nắp cống ướt (2001).
- 166–171 (đợt bổ sung): 166 "phỏng vấn visa" và 166 "phỏng vấn xin việc" cùng xoay quanh đến sớm và gửi xe (đồ được mang vào khác
  nhau); 169 "điểm check-in viral", 171 "chạy tới nơi mới biết đóng cửa" và 169 "Hồ Đại Lải: vào tự do hay cần vé" đều là xác minh quyền vào
  cửa; 170 "ngủ lại ngoài kế hoạch" gần 170 "chọn homestay" (khác ở chỗ không đặt trước).
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

## Dòng đã gỡ vì trùng nghĩa giữa hai mục (lần quét ngữ nghĩa thủ công trước khi chốt 500/225)

Validator đo trùng từ nên không bắt được các cặp cùng tình huống nhưng khác từ ngữ giữa hai mục (do hai tác giả
độc lập viết). Sau khi dựng matrix lần đầu, một lượt đọc cặp có điểm tương đồng cao nhất (tiêu đề + từ khóa + ý định)
đã gỡ 17 dòng VI và 6 dòng EN, giữ lại một dòng tốt hơn trong mỗi cặp; số thiếu được bù bằng chủ đề mới thật sự khác
(không paraphrase). Danh sách dòng đã gỡ (mục, tiêu đề):

**VI**

- 156 (TH-VI-0119): Cha mẹ chở con nhỏ bằng xe ga thuê: mũ, tư thế ngồi và những quy định cần tra trước
- 157 (TH-VI-0138): Xe côn tay dung tích lớn và hạng bằng lái: đối chiếu số cc trên giấy đăng ký với văn bản hiện hành
- 160 (TH-VI-0204): Nhận xe lúc trời đã tối: cách kiểm tra đèn pha, đèn hậu và xi nhan khi thiếu ánh sáng
- 162 (TH-VI-0255): Áo chống nắng, găng tay và khẩu trang chống nắng khi đi xe máy giữa trưa hè: chọn sao để vẫn quan sát tốt
- 162 (TH-VI-0258): Xuống xe khách ở Bến xe Gia Lâm với túi hành lý rồi lấy xe thuê: sắp xếp đồ sao cho chạy an toàn
- 162 (TH-VI-0263): Địa chỉ ngõ, ngách ở Hà Nội: gõ số nhà hay thả ghim vị trí khi nhờ giao xe hoặc tìm đường
- 162 (TH-VI-0273): Trang phục đi xe máy khi trời rét đậm ở Hà Nội: giữ ấm mà tay vẫn linh hoạt, tầm nhìn không bị che
- 163 (TH-VI-0289): Xe thuê đã có bảo hiểm trách nhiệm dân sự của chủ xe chưa: cách kiểm tra giấy chứng nhận còn hiệu lực
- 164 (TH-VI-0313): Nhường đường xe cứu thương và xe ưu tiên khi đang đi xe máy trong phố đông: nên làm gì cho an toàn
- 164 (TH-VI-0335): Xin gửi xe tháng ở chung cư hoặc tòa văn phòng khi xe thuê không đứng tên bạn
- 165 (TH-VI-0365): Phanh xe ga có phanh kết hợp: bóp tay phanh nào trước khi cần dừng gấp trên đường trơn
- 166 (TH-VI-0381): Người nhà ra Hà Nội chăm bệnh dài ngày: tuyến đi giữa nhà trọ, bệnh viện và chợ bằng xe máy
- 166 (TH-VI-0387): Đi làm ca ở khu công nghiệp ngoại thành bằng xe máy thuê: tuyến sáng sớm, xe tải và giờ đổi ca
- 168 (TH-VI-0437): Đi ăn nhậu cùng bạn bè: tính trước chỗ gửi xe thuê và cách về khi đã uống rượu bia
- 168 (TH-VI-0448): Đi xem ca nhạc hoặc bóng đá ở sân Mỹ Đình bằng xe máy: gửi xe, giờ tan sự kiện và đường về
- 169 (TH-VI-0459): Chạy xe dọc đê sông Hồng buổi chiều ngắm làng quê: kiểm tra mặt đường đê và mùa nước trước khi đi
- 171 (TH-VI-0486): Chia tiền xăng, vé và bữa ăn khi đi chơi nhóm bằng xe máy: ghi chép thế nào cho khỏi phiền lòng

**EN**

- 129 (TH-EN-0109): Tank Level at Handover: Record the Starting Gauge and Agree How Fuel Is Settled at Return
- 130 (TH-EN-0115): Can You Wash a Rental Scooter? What to Avoid Around Electrics, Seat Locks and Brakes
- 132 (TH-EN-0145): Leaving a Helmet With a Parked Scooter in Hanoi: Hooks, Seat Storage or Carry It With You
- 139 (TH-EN-0222): Vietnamese Public Holidays Beyond Tet: Plan Around Crowds and Closures in Hanoi
- 139 (TH-EN-0224): Choosing a Navigation App for Hanoi Riding: Motorbike Routing, Voice Prompts and Local Alternatives
- 139 (TH-EN-0225): Jet Lag and Your First Hanoi Ride: Plan a Gentler First Day Before Heavy Traffic

Bài học đã áp vào hướng dẫn soạn seed: trước khi thêm dòng, tự hỏi người tìm kiếm có thỏa mãn bằng một dòng đã có không; hai mục
cha-con khác nhau vẫn có thể viết cùng một tình huống (chăm người nhà ở bệnh viện, thẻ xe tháng, chở trẻ nhỏ, bảo hiểm trách nhiệm).
