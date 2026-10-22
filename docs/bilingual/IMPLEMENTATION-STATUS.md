# Trạng thái triển khai: workflow 500 VI + 500 EN

Nhánh làm việc: `feature/bilingual-500-workflow` (tách từ `brief/bilingual-500-taxonomy`, **không** từ `main` cũ).
Không có pull request nào được tạo; `main` không bị đụng; production publisher **vẫn tắt**.

## Phân loại trung thực

| Hạng mục | Đã implement | Đã test local | Đã cài lên website | Đã kiểm tra live |
|---|---|---|---|---|
| State schema 5 + migration từ schema 4 | có | có (unit + file cũ + remote giả lập CAS) | không áp dụng | chưa: state thật trên `factory-state` vẫn là schema 4, sẽ migrate ở lần mutate đầu tiên |
| Quota từng ngôn ngữ (499→500 qua, 501 chặn; intent chưa rõ kết quả tính như đã đăng) | có | có | không áp dụng | chưa: cần inventory qua adapter |
| Ưu tiên VI: claim, refill, brief, drain | có | có | không áp dụng | chưa |
| Chống chạy trùng nhiều phiên (lease, fence, claim nguyên tử, một WP slug mỗi topic) | có (đã có từ V4, mở rộng theo ngôn ngữ) | có (đa luồng + hết hạn lease) | không áp dụng | chưa |
| Checkpoint qua hết quota (submission bất biến, resume theo ngôn ngữ) | có | có | không áp dụng | chưa |
| QA song ngữ (nhãn ngôn ngữ, category, màn hình ngôn ngữ, link nội bộ cùng ngôn ngữ, claim/giá tiếng Việt, review có ngôn ngữ) | có | có | không áp dụng | chưa |
| Publisher qua adapter, readback đủ, không blind retry, không tính nháp/unknown | có | có (adapter giả lập) | chưa | **chưa** |
| Plugin `thuha-native-vi-publisher` 1.0.0 | có | có, trên **mô phỏng** WordPress (PHP 8.3) + mutation test | **chưa cài** | **chưa**: `RBHVI_Language`, Yoast, `wp_unique_post_slug`, permalink `/vi/` thật chưa được thấy |
| ZIP tái lập `dist/…zip` + SHA-256 | có | có (build lại từng byte) | chưa | không áp dụng |
| Kiểm tra archive cha/con, phân trang, sitemap, robots, cô lập ngôn ngữ | có (hàm thuần) | có (fixture local) | không áp dụng | **chưa**: publisher có quyền chạy sau bài đầu tiên |
| Matrix VI500 (500 mới) và EN500 (275 bảo vệ + 225 mới) | có | có (validator, chống trùng, URL/category) | không áp dụng | chưa: dedup live và dedup với 11 trang tĩnh VI cần inventory live |
| Nguồn nghiên cứu, review ý định, viết bài, review độc lập | **chưa làm** | không áp dụng | không áp dụng | không áp dụng |

**Chưa có bài nào được viết hoặc xuất bản.** 725 dòng matrix là kế hoạch, mọi dòng ở `NEEDS_SOURCE`:
không có nguồn nào được thu thập (không có kết nối WordPress/crawler trong phiên này và không được bịa),
chưa đo nhu cầu tìm kiếm (`demand_evidence: NOT_MEASURED`). Không được nói "đã có 1000 bài".

## Kiểm tra đã chạy (offline)

```
PYTHONPATH=src python3 -m unittest discover -s tests -v   # xem số test ở commit cuối bên dưới
PYTHONPATH=src python3 -m thuha.cli validate              # cấu hình, goal 500/500, matrix, gói adapter
php tests/php/run.php                                     # 17 tình huống plugin trên mô phỏng WordPress
python3 scripts/build_matrices.py                         # dựng lại + kiểm 2 matrix từ seed
python3 scripts/build_adapter_zip.py                      # dựng lại ZIP, test so từng byte
ruby -e 'require "yaml"; Dir[".github/workflows/*.yml"].each{|f| YAML.load_file(f)}'
```

Mutation test thủ công trên plugin (bỏ cổng ngôn ngữ category, chấp nhận phiên cookie, publish trước khi
gắn dấu VI): cả ba đều làm test PHP đỏ rồi trở lại xanh khi khôi phục, nên test không rỗng.

## Cần biết trước khi tin các con số

- 275 EN / 0 VI là **snapshot 2026-10-22**, không phải bộ đếm live. Số thiếu 500 + 225 là tạm tính.
- Quota đếm theo ID bài đã xuất bản từng ngôn ngữ **từ adapter**. Inventory từ REST public bị đánh nhãn
  `public-rest-unverified` và bị từ chối khi đếm, vì REST public có thể giấu bài VI.
- Hai chủ đề EN đã vào hàng đợi (`TH-000001`, `TH-000002`, PLANNED, trên `factory-state`) không phải bài
  đã đăng và được tính là chủ đề mở của EN; ma trận tránh trùng chúng.
- Kiểm tra trùng ý định của ma trận dựa vào độ trùng từ; các cặp gần nghĩa do tác giả tự báo nằm ở
  [MATRIX-REVIEW-NOTES.md](MATRIX-REVIEW-NOTES.md) và cần reviewer độc lập.

## Việc live còn PENDING (người giữ quyền publisher làm; không chặn việc offline)

1. Cài ZIP, tạo Application Password, `python3 -m thuha.cli --remote adapter-preflight`.
2. `audit` với thông tin xác thực để có inventory hai ngôn ngữ; so với màn hình WP-Admin.
3. Liệt kê 11 trang tĩnh VI (slug chưa biết) và điền `vi_url` trong `data/bilingual/service-targets.json`; chạy lại dedup.
4. Thu thập nguồn (`source --url`) → intent review → `intake`; viết/review bài bằng phiên AI thật.
5. Staging: một bài VI thử, xác nhận `/vi/`, hai dấu native, `<html lang>`, canonical, Yoast, sitemap.
6. Sau bài đầu của từng category: chạy `sitecheck` (archive cha/con, phân trang, sitemap, robots).
7. Quyết định riêng để bật `languages_enabled` (đề xuất pilot VI trước). Không làm trong lần này.

## Việc tiếp theo có thể làm ngay (không cần quyền live)

- Reviewer độc lập đọc `MATRIX-REVIEW-NOTES.md`, gộp/bỏ dòng trùng ý định, chạy lại `scripts/build_matrices.py`.
- Nếu một số dòng ở mục thiếu bị gộp, soạn thêm seed thật sự khác (xem `MATRIX-AUTHORING.md`), không paraphrase.
- `python3 -m thuha.cli matrix next --language vi --limit 10` cho danh sách chủ đề cần nguồn kế tiếp.

## Điểm dừng

Cập nhật ở cuối phiên: xem commit cuối của nhánh `feature/bilingual-500-workflow`
(`git log -1`) và bảng số liệu ngay dưới.

<!-- FINAL-NUMBERS -->
