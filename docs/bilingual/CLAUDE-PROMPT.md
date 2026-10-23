# Câu lệnh cho Claude — làm trong thuha-writer

Bạn làm trực tiếp trong repo `thuexemayhanoi/thuha-writer` cho website
https://rentbikehanoi.com. Đọc AGENTS.md, docs/bilingual/HANDOFF.md và toàn bộ
data/bilingual trước. Đây là brief mới thay mục tiêu cũ 2000 bài English-only.

Hãy hoàn thiện workflow **500 bài tiếng Việt trước, sau đó bù tiếng Anh để toàn
website có 500 bài EN + 500 bài VI**. Snapshot mới: 275 EN publish, 0 VI post;
11 trang VI là page, không tính vào 500. Tạm cần 500 VI +225 EN, nhưng số thiếu
phải tính lại live ở publisher. Hai ngôn ngữ viết bản địa theo nhu cầu tìm kiếm,
không dịch máy, không sao chép bài blog khác, không gọi API AI trả phí.

Tôi đã tạo chuyên mục thật trên WordPress. Dùng manifest trong repo có ID,
parent, slug, URL và mô tả; không tạo lại, không đổi URL/canonical/category cha
hoặc sửa 275 bài cũ. Lập matrix VI500 theo 20 mục con đã có và matrix EN500
bao gồm existing được bảo vệ + new cần bù. Đề tài phải có intent riêng, dedup
với cả bài và trang dịch vụ; không chỉ thay quận/phường, mẫu xe hay viết lại
cùng một câu hỏi cho đủ số. plan.json là phân bổ gợi ý, không phải lệnh nhồi bài.

Bạn chỉ cần GitHub. Bạn không có kết nối WordPress/crawler của tôi: không để
việc đó chặn code, matrix, viết bài hay offline QA. Dùng snapshot đã cung cấp;
khai rõ bước live nào PENDING. Nguồn nghiên cứu cần evidence thật: không vào
được thì lưu NEEDS_SOURCE để tiếp tục sau, tuyệt đối không giả kết quả crawl.

Hãy triển khai đầy đủ vào code hiện có, không chỉ tạo tài liệu: hỗ trợ hai
ngôn ngữ trong state/lease/queue/claim/submit/review/QA/audit/publisher/report,
đếm quota từng ngôn ngữ, ưu tiên VI, chống chạy trùng nhiều phiên, checkpoint
qua lúc hết quota, sửa lỗi có giới hạn, dừng đúng 500 mỗi ngôn ngữ. Giữ cơ chế
reconcile sau timeout, không blind retry POST, không tính draft/unknown là bài
đã publish thành công. Chưa bật publisher production trong lần triển khai này.

Đặc biệt đọc contract native VI: post cần private taxonomy rbhvi_language=vi;
category VI một mình không đủ, trường language giả trong core REST không chạy.
Hãy viết và đóng gói ZIP companion plugin riêng trong repo để publisher có API
có xác thực gắn marker trước publish và đọc inventory đủ hai ngôn ngữ. Dùng
WordPress API và RBHVI_Language::set_vi, không SQL hay endpoint công khai.
Plugin native VI đang có sẵn trên website; không thay bằng plugin dịch ngoài,
không bắt sửa tay hosting. Nếu adapter chưa cài thì ghi rõ live publishing
BLOCKED_ADAPTER_NOT_DEPLOYED, vẫn làm xong tất cả việc offline có thể làm.

EN giữ ở gốc; VI bài /vi/slug/, category /vi/chuyen-muc/slug/. Category có
parent thật nhưng URL VI hiện phẳng, không tự ghép URL cha/con khác manifest.
Title/meta/H1/alt/internal links viết đúng ngôn ngữ. Canonical tự trỏ; chỉ ghép
hreflang khi hai bài thật tương đương. Bài Việt độc lập đã được cho phép vào
sitemap, không cần tạo bài Anh giả để ghép. Kiểm tra archive cha/con, sitemap,
robots, phân trang và language isolation bằng fixture local, còn live để
publisher có quyền thực hiện sau. Giữ mọi cổng chất lượng hiện có, không hạ
ngưỡng chỉ để đạt 1000 bài. Cập nhật của chủ website ngày 23/10: bỏ cổng AI review độc lập;
bản thảo hoàn chỉnh chạy QA tự động >=75/100 + chống trùng + đúng danh mục/ngôn ngữ rồi publisher.
Không chờ reviewer, không giả review và không cộng điểm review. Lỗi nghiêm trọng vẫn chặn; bài WAITING_DATA/HELD
không được biến thành READY khi chưa đủ dữ liệu. Lưu review cũ như lịch sử, không dùng làm điều kiện xuất bản.

README.md, AGENTS.md, docs vận hành, config và workflow phải nói cùng một
mục tiêu. Xóa mâu thuẫn 2000/en-US-only ở phần đang có hiệu lực, giữ lịch sử có
nhãn rõ. W1–W9 chỉ là slot điều phối nếu không có phiên AI thật đang chạy;
không tuyên bố cron GitHub tự viết bài bằng AI. Không yêu cầu tôi thao tác kỹ
thuật hay đăng ký dịch vụ khác để thay việc bạn có thể làm trong repo.

Tự chạy kiểm tra phù hợp: quota 499→500 và chặn 501 từng ngôn ngữ; existing
posts được tính; pages/draft/trash bị loại; VI priority; resume sau hết quota;
no duplicate after unknown POST; category/language mismatch; adapter auth;
EN không lẫn VI; matrix500VI +500EN có URL/category hợp lệ. Không tạo test chỉ
để mirror code. Không đẩy secrets hoặc nội dung test lên website thật.

Làm đến khi code, matrix, bản đóng gói và kiểm tra offline hoàn chỉnh. Trước
khi hết quota, commit checkpoint nêu việc đã xong, đúng file/ID đang dở và
câu lệnh tiếp tục. Báo cuối ngắn gọn bằng tiếng Việt, phân biệt chính xác
đã implement / đã test local / chưa cài / chưa kiểm tra live. Không nói đã
publish 1000 bài khi mới tạo matrix hoặc chạy unit test.
