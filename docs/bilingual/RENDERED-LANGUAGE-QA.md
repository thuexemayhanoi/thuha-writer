# ThuHa Writer — Kiểm tra ngôn ngữ VI–EN trước và sau xuất bản (24/10/2026)

> **Tài liệu vận hành hiện hành**, chỉ áp dụng cho `thuexemayhanoi/thuha-writer` → `https://rentbikehanoi.com/`. Đọc [AGENTS.md](../../AGENTS.md) và [config/qa.json](../../config/qa.json) trước. Không thay thế hoặc sửa dữ liệu lịch sử trong `factory-state`.

## Phân tách trách nhiệm

| Giai đoạn | Đã được code xử lý | Khi sai |
| --- | --- | --- |
| **Writer / trước submit** | Topic ID, `language` (`vi` hoặc `en-US`), URL và taxonomy đồng ngôn ngữ; kiểm tra title, `seo_title`, `meta_description`, `focus_keyword`, body, link nội bộ bằng `src/thuha/quality.py` và `src/thuha/language.py` | **Hard failure**; không được READY/publish dù điểm QA ≥75 |
| **Adapter / trước publish** | Tạo nháp đúng title/body, gắn native VI marker trước khi publish, ghi và đọc lại SEO Yoast, bảo đảm permalink ở `/vi/{slug}/` hoặc gốc cho EN | Giữ bản nháp hoặc trả lỗi; không tự đoán đường dẫn |
| **WordPress read-back** | Đối chiếu dữ liệu lưu trong WordPress (ngôn ngữ, marker, taxonomy, title, body, Yoast) với bài được QA | Ghi `integrity=MISMATCH`, cảnh báo chặn bài **mới** đến khi kiểm tra và acknowledge |
| **Trang public / sau publish** | `canonical`, SEO title, meta description, `<html lang>`, hreflang, schema, indexability **và từ 24/10: đúng một H1, khớp tiêu đề gốc của bài Writer, phù hợp ngôn ngữ** | `post_check=WARNING`, thử lại có giãn cách; `FAILED_FINAL` nếu 5 lần không đạt; **không hủy receipt PUBLISHED hoặc chặn toàn bộ queue** |

## Quy tắc địa chỉ

- EN: `https://rentbikehanoi.com/{ascii-slug}/`, locale nội dung `en-US` (HTML lang bắt đầu bằng `en`).
- VI: `https://rentbikehanoi.com/vi/{ascii-slug}/`, locale nội dung `vi` (HTML lang bắt đầu bằng `vi`).
- Không đổi slug, URL, canonical, nội dung cũ, không tạo bản dịch tự động. Hreflang chỉ dùng nếu cặp tương đương thực sự tồn tại.
- **Site Title / Tagline trong WordPress Settings → General là cấu hình toàn cục**, không phải `seo_title` của từng bài. Không sửa hai ô đó từ Writer. SEO title và meta description luôn theo ngôn ngữ bài.

## Quy tắc kiểm tra H1 public

Hàm `src/thuha/sitecheck.py::check_rendered_post_language` nhận dữ liệu HTML đã được phân tích, tiêu đề bài nguồn và ngôn ngữ. Nó báo:
- `PUBLIC_H1_COUNT_0` (không có H1); `PUBLIC_H1_COUNT_2` và các số khác nếu có nhiều H1.
- `PUBLIC_H1_TITLE_MISMATCH`: H1 hiển thị không trùng với title gốc của bài đã QA (so sánh sau chuẩn hóa whitespace).
- `PUBLIC_H1_LANGUAGE_MISMATCH`: tín hiệu từ bộ kiểm tra ngôn ngữ cho thấy H1 không phù hợp VI/EN.

Hàm được gọi từ `Publisher.crawl()`, không sửa bài, không đổi Yoast, không viết WordPress. `<title>` HTML (SEO title) được đối chiếu **riêng** với `article['seo_title']`; H1 đối chiếu với `article['title']`. Những bộ kiểm tra ngôn ngữ bằng heuristics không thể chứng minh chất lượng biên tập của văn bản.

**Giới hạn quan trọng:** Bước H1 mới **không** kiểm tra hết các dòng chữ trong giao diện dùng chung như menu, breadcrumb, TOC “Table of Contents”/“Hide”, footer, nút, widget hoặc Site Title/Tagline. Những lỗi này phải giao cho theme hoặc plugin đa ngôn ngữ sửa ở template/component dùng chung, không yêu cầu Writer thay nội dung hàng nghìn bài.

## Vận hành và khôi phục

1. Trước khi viết, đọc [CLAUDE-PROMPT.md](CLAUDE-PROMPT.md), lấy topic bằng `next/claim`, `pack`, viết đúng ngôn ngữ rồi `build → precheck → submit`. QA vẫn **≥75 và không có hard failure**. Ảnh/alt tùy chọn.
2. Publisher tự động phải xác minh từ WordPress adapter và receipt. Không gọi bài là PUBLISHED chỉ vì PASS hoặc vì GitHub Actions chạy xanh.
3. Khi cần xác minh public page, dùng chế độ xác minh hiện hành: `PYTHONPATH=src python3 -m thuha.cli --remote publisher --mode verify --topic-id TH-VI-0001` (thay ID bằng topic có receipt). Chỉ chạy khi có quyền truy cập thật; không giả lập kết quả.
4. Nếu `post_check` báo H1 lỗi, đối chiếu HTML public với title nguồn, cache và theme/plugin; sửa phần render ở repo/theme thích hợp, sau đó chạy lại hậu kiểm. Lưu ý lịch retry: **10 phút → 30 phút → 1 giờ → 3 giờ**, tối đa 5 lần.
5. Không đánh đồng `post_check=WARNING` với `integrity=MISMATCH`: chỉ *stored readback integrity mismatch* mới tạo cảnh báo có thể chặn các publication mới. Không acknowledge cho đến khi đã kiểm tra thực tế.

## Test và bằng chứng

- Unit tests: `tests/test_sitecheck.py` (H1 đúng/sai ngôn ngữ, thiếu/nhiều H1).
- Publisher tests: `tests/test_factory.py` và `tests/fake_wordpress.py` (public H1 đúng và trường hợp theme render sai).
- Bản sửa mã nguồn đã merge ở [PR #11](https://github.com/thuexemayhanoi/thuha-writer/pull/11), commit `638f51e20a0beea0df255bd24aa77edfa708caa5`. Đây là bằng chứng kiểm thử giả lập/CI, **không** phải bằng chứng rằng giao diện public hiện tại đã hết tiếng Anh.
- Đọc tình trạng production từ receipt mới và WordPress thật; snapshot tài liệu cũ không được xem là số realtime.
