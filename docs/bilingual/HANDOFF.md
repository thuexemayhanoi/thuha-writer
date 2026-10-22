# Bàn giao workflow hai ngôn ngữ — rentbikehanoi.com

> **Cập nhật triển khai (nhánh `feature/bilingual-500-workflow`):** runtime, matrix, plugin kết nối và test offline
> đã làm xong trong repo; xem [IMPLEMENTATION-STATUS.md](IMPLEMENTATION-STATUS.md) (commit, kiểm tra đã chạy, việc dang dở,
> việc live còn PENDING), [ADAPTER.md](ADAPTER.md) và [MATRIX-AUTHORING.md](MATRIX-AUTHORING.md). Phần "Phạm vi Claude phải
> thực hiện" bên dưới là yêu cầu gốc, giữ nguyên làm hợp đồng. Mọi mục "đã làm trên WordPress thật" là quan sát của
> phiên trước; phiên này không có kết nối WordPress nên không xác nhận lại.

## Việc đã làm trên WordPress thật

Thời điểm: 2026-10-22 UTC / 23-10-2026 Việt Nam.

- Đếm bằng dữ liệu WordPress: **275 post tiếng Anh đã publish, 0 post tiếng
  Việt**. Hai auto-draft không được tính; 11 trang tĩnh Việt không phải bài blog.
- Tạo **49 category mới: 22 EN + 27 VI**. Giữ nguyên 10 category cũ, đường dẫn,
  quan hệ cha-con và bài hiện có. Tổng 59 category gồm Uncategorized.
- VI: một gốc `cam-nang` (#140), sáu nhóm cha (#146–151), 20 nhóm con (#152–171).
  Tất cả 27 mục có `_rbhvi_lang=vi`, kiểm tra lại qua dữ liệu WordPress.
- EN: mở rộng cấu trúc Blog hiện có; hai nhóm mới về so sánh xe và an toàn,
  20 mục con mới; không đổi parent của mục cũ.
- Lưu thiết lập plugin `rbhvi_settings.sitemap_pairs_only=false` qua UI plugin,
  đọc lại xác nhận. Bài Việt độc lập không phải ghép cặp giả để được vào sitemap.
- Không xuất bản bài mới, không di chuyển bài cũ, không bật publisher.

`data/bilingual/live-categories-2026-10-22.json` là manifest ID, slug, parent,
description và URL thực do WordPress trả về. `taxonomy-map.csv` thêm full path,
vai trò hub/leaf, ngôn ngữ và phân bổ đề tài gợi ý. Không lấy tổng category.count
làm tổng bài: một bài có thể ở nhiều category; cha có thể bao gồm bài ở con.

Các mục mới tạm rỗng theo yêu cầu chủ website. Manifest xác nhận term đã tồn
tại, không phải xác nhận mọi archive rỗng đã được Google index. Không đưa hàng
loạt mục rỗng vào menu. Kiểm tra HTTP/canonical/robots, archive cha chứa bài con,
sitemap và phân trang khi có bài đầu tiên; nếu cần noindex mục rỗng thì phải
chuyển sang index sau khi có nội dung, không để cờ noindex tồn tại vĩnh viễn.

Đã mở archive `/vi/chuyen-muc/huong-dan-thue-xe/` qua trình duyệt: đúng tiêu đề,
mô tả Việt, breadcrumb về gốc Cẩm nang, giao diện Việt và thông báo chưa có bài.
Sidebar còn nhãn `Latest Posts` tiếng Anh từ theme; đây là việc Việt hóa giao
diện cần chuyển cho phiên theme, không phải bằng chứng đã có bài VI.

## Đếm và thứ tự

Đích cuối: **500 EN tổng cộng + 500 VI tổng cộng**, không phải thêm 500 EN.
VI trước: hiện thiếu 500. EN sau: snapshot hiện thiếu 225. Publisher phải lấy số
live mới, cộng cả reservation/unknown outcome để tránh vượt trần hoặc tạo trùng.
Chỉ POST mới do workflow sở hữu được xử lý; không sửa bài cũ để đạt chỉ tiêu.
Nếu bên khác xuất bản thêm, tự giảm phần còn thiếu. Không coi đủ 500 bài là
bằng chứng SEO tốt hay cam kết lên hạng.

Nguồn public inventory 275 bài: `data/bilingual/live-posts-2026-10-22.json`.
Audit sâu cũ `reports/live-audit/inventory.json` có 273 bài ở thời điểm trước,
gồm headings, chữ ký nội dung, liên kết, ảnh; dùng bổ sung dedup, không thay số
live 275. Trước phát hành, publisher cập nhật toàn bộ inventory cả hai ngôn ngữ
và trang tĩnh, vì public REST có thể bị bộ lọc native VI tách ngôn ngữ.

## Nguồn tham khảo đã đối chiếu

- `wp-writer`: workflow của thuexemaynguyentu.com; `data/topics.jsonl` có 961
  topic, không phải bộ 500 EN + 500 VI. Chỉ tham khảo kiến trúc và taxonomy.
- `wp-aiwriter`: workflow blog.rentbikehanoi.com; `en/topics.json` có **500 đề
  tài EN**, `data/topics.json` hiện có **355 dòng VI, ID146–500**. Không coi
  các dòng này là bài đã xuất bản, không bịa thêm 145 bài legacy còn thiếu.
- `data/bilingual/reference-en-ideas.json` và `reference-vi-ideas.json` là
  ý tưởng được rút gọn, bỏ category ID, URL publish và trạng thái nguồn.
  Tất cả phải nghiên cứu, chỉnh ý định và chống trùng lại cho domain đích.
- Nguồn blog có VI ở gốc, EN ở `/en/`. **KHÔNG** mang routing đó qua đây.
  Đích rentbikehanoi.com có EN ở gốc, VI ở `/vi/`.

## Contract native VI cho publisher

Website dùng theme riêng và plugin `rentbikehanoi-native-vi` 1.0.0. Yoast quản
lý SEO; plugin riêng tách ngôn ngữ và nối cặp khi tương đương.

| Dữ liệu | Contract đang chạy |
| --- | --- |
| Post tiếng Anh | Giữ permalink hiện có ở gốc, không có marker VI |
| Post tiếng Việt | `/vi/{slug-khong-dau}/` |
| Category VI | `/vi/chuyen-muc/{slug}/` |
| Phân cấp VI | `parent` thật trong WordPress; URL hiện dùng slug phẳng, không nối toàn bộ ancestor |
| Marker category | termmeta `_rbhvi_lang=vi` |
| Marker post | private taxonomy `rbhvi_language`, term slug `vi` |
| Pair nếu thật sự tương đương | meta `_rbhvi_pair` ở phía VI; dùng API/hàm chính thức của plugin |
| API PHP phân ngôn ngữ | `RBHVI_Language::set_vi($post_id, true)`; `is_vi`, `term_is_vi` để kiểm tra |
| Sitemap bài VI độc lập | Đã tắt `sitemap_pairs_only` |

Taxonomy ngôn ngữ **show_in_rest=false**. Core REST `/wp/v2/posts` hiện không
có một trường `language=vi` đã được kiểm chứng. Không viết một trường giả rồi
coi là đã gắn ngôn ngữ. Chọn category VI không tự biến bài thành VI.

Vì Claude chỉ có repo này, cần triển khai **adapter/companion plugin riêng**
trong repo, đóng ZIP, hướng dẫn cài bằng WordPress, không sửa tay hosting.
Adapter phải phụ thuộc native VI, dùng WordPress API/hàm native đã nêu,
kiểm tra quyền edit_posts/publish_posts và quyền với từng post, giới hạn origin
và đối tượng do factory sở hữu, schema validation và language/category match.
Không đăng ký endpoint công khai, không ghi SQL hay cho thực thi PHP tùy ý.
Tạo draft có ownership/idempotency marker trước, gắn VI và SEO rồi publish;
không được xuất bản tạm ở URL EN rồi đổi sang VI. Retry kết quả không rõ phải
reconcile theo marker, không POST lại. Hỗ trợ read-only inventory cả EN+VI cho
publisher, thay vì tin query public luôn trả đủ. Endpoint mới phải có contract,
test thiếu quyền/sai ngôn ngữ và readback đầy đủ; chưa deploy phải báo PENDING.

Nội dung mới dùng canonical tự trỏ về URL ngôn ngữ của mình, title/meta/H1/
ảnh alt/internal links cùng ngôn ngữ. Chỉ tạo hreflang cặp tương đương hai chiều
đã tồn tại; không ghép bài khác ý định chỉ vì đủ số. Không cài plugin dịch ngoài,
không gọi AI/translation API. WordPress REST có xác thực của publisher là cơ
chế xuất bản hiện có, không phải dịch vụ AI trả phí.

## Phạm vi Claude phải thực hiện

1. Đọc code hiện tại rồi lập danh sách chỗ hard-code 2000/en-US; đổi đồng bộ
   project/factory/release ceilings, runtime, coordinator, audit, QA, publisher,
   dashboard, docs và test sang đích 500/language. Giữ production OFF.
2. Tạo matrix VI500 có ID riêng, native Vietnamese intents, category ID/URL thật,
   hub, keyword, intent, draft slug/URL, service target, internal-link plan,
   source requirements, dedup status, priority, writer state/checkpoint.
3. Tạo matrix EN tổng500 gồm 275 EXISTING_PROTECTED + phần còn thiếu NEW;
   không tái tạo 275 bài. Snapshot có thể thay đổi nên các con số là dynamic.
4. Dùng phân bổ `plan.json` làm ngân sách biên tập gợi ý, không nhồi đủ bài
   bằng paraphrase, cùng một bài khác tên khu vực hoặc thay tên mẫu xe.
5. Offline QA và CI không crawl WordPress bắt buộc. Nghiên cứu nguồn chỉ khai
   đã đọc khi có evidence thật; bị chặn thì checkpoint NEEDS_SOURCE, không bịa.
6. Credentialed publisher thực hiện live preflight/readback; W1–W9 viết, review,
   sửa và lưu checkpoint qua phiên AI thật. GitHub Actions không có AI runtime
   thì chỉ điều phối, không được báo tự sinh bài bằng AI từ cron.
7. Handoff cuối có ZIP adapter, diff, checks, matrix validation, README/AGENTS
   đồng bộ và danh sách rõ việc đã thử local / chưa deploy / chưa test live.

Không cần Claude truy cập repo khác: nguồn tham khảo rút gọn và contract nằm
ngay đây. Không yêu cầu chủ website đi đăng ký crawler để hoàn thành phần code.
