# Những câu chỉ chủ cửa hàng trả lời được

Các bản thảo tiếng Việt hiện chỉ dựa vào thông tin chủ cửa hàng đã cung cấp (tên, địa chỉ, giờ mở cửa, số điện thoại, khoảng giá tham khảo). Phần lớn
chủ đề còn lại là chuyện cửa hàng làm thế nào, và đó là điều tôi không được và không thể tự suy ra. Vì vậy các bài hiện là danh sách câu hỏi cho khách
hàng đem đi hỏi chính cửa hàng. Nếu chủ cửa hàng trả lời được những câu dưới đây bằng vài chữ, mỗi câu mở khóa một nhóm bài có câu trả lời thật thay vì chỉ có câu hỏi.

Không cần cài đặt hay chạy lệnh gì: chỉ cần trả lời bằng chữ, mỗi câu một hai dòng. Câu nào chưa có quy định thì ghi rõ "chưa có quy định, tùy từng trường hợp".

| # | Câu hỏi | Mở khóa |
|---|---|---|
| 1 | Một ngày thuê tính theo đủ 24 giờ kể từ lúc nhận xe, hay theo ngày lịch? Có thời gian ân hạn khi trả muộn không, và quá thì tính thế nào? | TH-VI-0004, 0093, 0105, các bài về giờ nhận trả |
| 2 | Trả xe sớm hơn dự kiến thì xử lý thế nào (gói ngày, gói tuần, gói tháng)? Đổi từ gói ngày sang gói tuần giữa chừng được không, tính từ ngày nào? | TH-VI-0006, 0019, 0003, 0062, 0072 |
| 3 | Cửa hàng có thu cọc không? Nếu có: bao nhiêu (theo loại xe), hình thức giữ, có khoản giữ chỗ riêng khi đặt trước không? | TH-VI-0033, 0053, 0024 (đã giữ), 0043 |
| 4 | Cọc được hoàn khi nào và bằng cách nào (tiền mặt hay chuyển khoản)? Những khoản nào có thể bị trừ? | TH-VI-0035, 0095, 0036 |
| 5 | Mức đền bù khi hỏng hoặc mất đồ: có bảng mức cố định không, hay tính theo hóa đơn sửa? Gồm những hạng mục nào (xước, gương, đèn, chìa khóa, mũ...)? | TH-VI-0011, 0049, 0211, các bài sự cố |
| 6 | Phụ phí: trả muộn, nhận hoặc trả ngoài giờ mở cửa, giao nhận xe tận nơi, thuê thêm mũ hoặc phụ kiện, gia hạn, vệ sinh xe, hủy hoặc đổi lịch: khoản nào có, bao nhiêu? | TH-VI-0014, 0101, 0102, 0103 |
| 7 | Giá thuê đã gồm những gì (mấy mũ bảo hiểm, áo mưa, khóa phụ, giá đỡ điện thoại)? Quy ước xăng khi nhận và trả xe là gì? | TH-VI-0010 (đang giữ), 0255, 0089 |
| 8 | Cách thanh toán nào được nhận (tiền mặt, chuyển khoản, quét mã)? Tên chủ tài khoản nhận tiền là gì, kênh liên hệ chính thức nào ngoài số điện thoại (Zalo, Facebook, website)? | TH-VI-0009, 0043, 0016, 0097 |
| 9 | Xác nhận khoảng giá tham khảo: với xe số, giá một tháng (1.000.000-1.200.000 đồng) thấp hơn hai tuần (1.400.000-1.600.000 đồng); với xe ga, giá tuần tối đa 1.000.000 đồng so với giá ngày 150.000-200.000 đồng. Đó là đúng ý hay có nhầm lẫn khi nhập? | TH-VI-0019, 0058, 0016 (các bài đang dùng đúng các con số này) |
| 10 | Thuê tháng: trả một lần hay chia kỳ? Bảo dưỡng giữa kỳ do ai lo, có xe thay thế không? Người thuê và người lái có phải là một người không, cần mang giấy tờ gì? | TH-VI-0063, 0217, 0058, các bài thuê tháng |

Khi có câu trả lời, nơi ghi đúng là `config/business-facts.json` (một thay đổi cần được xem xét như mọi thay đổi cấu hình). **Lưu ý:** bằng chứng first-party của các bản thảo hiện tại gắn
với bản ghi hiện có của tệp đó; khi tệp đổi, bằng chứng cũ được coi là cũ và các bản thảo phải được viết lại dựa trên câu trả lời thật (đó chính là mục đích: chuyển từ
"hãy hỏi cửa hàng" sang "cửa hàng cho biết"). Không bài nào được xuất bản chỉ vì câu trả lời đã có: vẫn cần ảnh có alt tiếng Việt, liên kết nội bộ đã xác thực, inventory từ adapter,
QA tự động >=85/100, không chờ AI review độc lập (yêu cầu chủ website ngày 23/10).
