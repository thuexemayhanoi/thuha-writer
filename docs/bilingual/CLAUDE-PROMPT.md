> **Cập nhật 23/10/2026 (ưu tiên áp dụng):** Ảnh/alt hoàn toàn tùy chọn. Claude không cần xem hoặc tìm ảnh WordPress; `featured_media: null` nộp, QA và xuất bản bình thường, không đợi `FEATURED_MEDIA`. Các mô tả lịch sử dưới đây về bắt buộc ảnh/alt không còn hiệu lực. Xem [quy định mới](../MEDIA-OPTIONAL-POLICY.md).

# ThuHa Writer — hướng dẫn HIỆN HÀNH cho Claude/ChatGPT Work (23/10/2026)

> **Đọc `AGENTS.md` trước.** Đây là hướng dẫn vận hành cho **phiên writer mới**, thay thế brief xây dựng workflow 500 VI/500 EN cũ. Không yêu cầu sửa lại toàn bộ code hay tự tạo ma trận từ đầu.

## Phạm vi và chính sách

- Chỉ thao tác trong GitHub `thuexemayhanoi/thuha-writer` cho website **https://rentbikehanoi.com/**. Tuyệt đối không nhầm `/wp-aiwriter`, GitHub người khác, blog khác, URL, WordPress ID, category ID, Secrets hay ledger.
- Mục tiêu: tổng cộng **500 bài EN + 500 bài VI đã publish**, bao gồm bài đang có trên site, **không phải 500 bài mới bằng mọi giá**. EN ở gốc; VI ở `/vi/{ascii-slug}/`; không dịch máy, không tự tạo cặp ngôn ngữ giả.
- **VI được ưu tiên**, nhưng nếu chưa có VI đủ điều kiện, hãy viết EN có chứng cứ thật, thay vì kẹt vô hạn chờ hoàn thành toàn bộ 500 VI.
- QA kỹ thuật chung `config/qa.json`: **từ 75/100 trở lên PASS**, dưới 75 FAIL, mọi `hard_fails` vẫn chặn. Không chờ AI reviewer/owner duyệt từng bài và không cộng điểm reviewer giả.
- Publisher **đã được chủ site bật**: `auto-scale`, tối đa **50 bài/ngày** ở thời điểm ghi hướng dẫn. Chỉ GitHub Actions + WordPress adapter đã được xác thực mới đăng và xác minh; writer không tự tuyên bố đã publish. GitHub Environment và biến `THUHA_GO_LIVE_APPROVAL` không còn dùng; WordPress Secrets thuộc riêng repo này.
- Checkpoint đã kiểm tra 23/10/2026: shared ledger `factory-state` v448 có **9 biên nhận PUBLISHED EN, 0 READY; 51 EN + 14 VI PLANNED; 7 EN + 21 VI WAITING_DATA; 11 VI HELD; 0 lease**. **Đây không phải số liệu realtime.** Đọc ledger mới nhất khi bắt đầu; không dùng snapshot 275 EN/0 VI hoặc tài liệu V4/V5 làm số hiện hành.

## Công việc của writer trong phiên này

1. Xác minh owner/repo/branch, đọc `AGENTS.md`, `config/qa.json`, `config/release.json`, `docs/V5-WRITER-BRIEF.md` và tình trạng shared `factory-state`. Nếu làm trong branch riêng qua CLI `--git-branch`, chạy **`PYTHONPATH=src python3 -m thuha.cli --git-branch sync --apply`** trước khi nhận bài. Nếu `DIVERGED`, không ghi đè trạng thái chung; báo tình huống và giải quyết theo contract.
2. Dùng `--git-branch next --language vi` hoặc `... next --language en` tìm bài có thể làm thật. Chọn chủ đề đủ dữ liệu rồi `claim --session <SESSION> --agent-id <AGENT> --slot auto` (hoặc `--topic-id <ID>` để lấy chủ đề hợp lệ riêng). Giữ `slot`, `fence` và **heartbeat lease**. `W1–W9` chỉ là slot, không phải có sẵn chín tác tử chạy ngầm.
3. `pack --topic-id <ID> --out pack.json`. Kiểm chứng nguồn đã capture, ý định tìm kiếm riêng, business facts và category/URL thật. Đọc nguồn bằng **công cụ đang thực sự có trong phiên**, không áp dụng session ID/model cụ thể của Claude đời trước. Chỉ ghi evidence khi có lần fetch thành công; tuyệt đối không tự bịa URL, số liệu, giá, luật, review hay ảnh. Không có nguồn thì `NEEDS_SOURCE`.
4. Viết bài bản địa theo ngôn ngữ và topic đã claim. Để `featured_media: null` nếu Claude không truy cập ảnh WordPress; không yêu cầu tìm ảnh/alt; cần ít nhất **2 liên kết nội bộ hợp lệ** cùng ngôn ngữ, trong đó có **1 liên kết tới nội dung đang sống**, không dùng category archive làm thay thế. Tôn trọng canonical, slug, taxonomies và Yoast.
5. `build --topic-id <ID> --body body.html --meta meta.json`, rồi `precheck --topic-id <ID> --file article.json`; sửa lỗi nội dung cho QA75, không cố chấm điểm bằng cách bịa nội dung. Sau đó `submit --slot <SLOT> --session <SESSION> --fence <FENCE> --file article.json`.
6. Nếu bài chỉ thiếu dữ liệu site mà writer không thể tạo được (liên kết VI, inventory xác thực), dùng `submit ... --waiting-for auto` **khi precheck cho phép**; lưu `WAITING_DATA`, không giả PASS. `HELD` không tự mở. Chọn chủ đề khác có thể viết; nội dung bịa hoặc lỗi kỹ thuật phải sửa chứ không gắn nhãn chờ để lách QA.
7. Commit checkpoint và document đúng quy trình của repo, đưa branch qua PR/main để `promote` fast-forward sang `factory-state`; **nhánh writer chưa hand-over thì Publisher không nhìn thấy bài**. Tránh sửa ledger, receipt, bài live hoặc force-push chung. Kết thúc báo cáo ID bài, trạng thái thực, nguồn, SHA và các thiếu hụt còn lại.

## Không được hiểu nhầm

- Không bật/tắt release hoặc sửa Secrets, sửa pipeline, code, theme, plugin, post live khi chỉ được giao nhiệm vụ viết.
- Không dùng tài liệu `docs/WP-AIWRITER-ADAPTATION.md` hoặc brief reviewer V5 như lệnh mới: chúng là **lịch sử**.
- `docs/bilingual/OWNER-QUESTIONS.md` là danh sách xác nhận **dữ kiện cửa hàng cụ thể**, không phải khóa duyệt mỗi bài. Chủ đề khác đủ bằng chứng vẫn có thể tiếp tục.
- Một bài QA PASS chưa chắc được đăng; chỉ gọi PUBLISHED khi đã có biên nhận WordPress xác minh trong shared ledger.
- Nếu quota Work cạn, lưu và commit đúng bài đã hoàn thành, ghi cách resume, không tự báo AI đang chạy nền.
