# Plugin kết nối xuất bản `thuha-native-vi-publisher`

Plugin đồng hành này là **đường ghi duy nhất** của workflow vào rentbikehanoi.com.
Nó tồn tại vì ba lý do trong brief: bài Việt cần dấu `rbhvi_language=vi` gắn **trước**
khi xuất bản, REST public không đáng tin để đếm bài Việt, và `/wp/v2/posts` của core
không có trường ngôn ngữ đã kiểm chứng.

> **Trạng thái trung thực:** plugin đã viết, đóng gói và chạy thử trên **mô phỏng
> WordPress** trong repo. Chưa cài lên website, chưa gọi `RBHVI_Language` thật,
> chưa chạy với Yoast thật. Mọi thứ liên quan đến website thật là **PENDING**.

## Cài đặt (làm trong giao diện WordPress, không sửa tay hosting)

1. Lấy file `dist/thuha-native-vi-publisher-1.0.0.zip` (SHA-256 nằm ở
   `dist/thuha-native-vi-publisher-1.0.0.zip.sha256`).
2. WordPress Admin → **Plugins → Add New → Upload Plugin** → chọn ZIP → **Activate**.
   Plugin `rentbikehanoi-native-vi` phải đang bật; nếu không, mọi route trừ
   `/preflight` trả `503 thuha_native_vi_missing` và có thông báo trong admin.
3. Tạo **Application Password** cho một người dùng có quyền xuất bản bài
   (Users → Profile → Application Passwords). Không dùng tài khoản quản trị chung nếu
   có thể tạo vai trò Editor riêng.
4. Chủ website (hoặc người giữ secret) đặt user và application password vào secret của
   môi trường `thuha-production` trên GitHub (`THUHA_WP_USER`,
   `THUHA_WP_APPLICATION_PASSWORD`). Không dán vào repo, issue, log hay prompt.
5. Publisher có thông tin xác thực chạy `python3 -m thuha.cli --remote adapter-preflight`.
   Chỉ khi lệnh này thành công, trạng thái adapter trong state mới là `VERIFIED`.
   Cho tới lúc đó dashboard báo `BLOCKED_ADAPTER_NOT_DEPLOYED`.
6. Bật production là quyết định riêng (`config/release.json`, `languages_enabled`);
   lần triển khai này **không** bật.

## Hợp đồng REST (`/wp-json/thuha-writer/v1`, contract `thuha-writer/1`)

| Route | Quyền | Việc |
|---|---|---|
| `GET /preflight` | `edit_posts` | phiên bản, API native VI, Yoast, quyền, `sitemap_pairs_only` |
| `GET /inventory?type=post\|page&status=…&page=&per_page=` | `edit_posts` | danh sách đầy đủ **cả hai ngôn ngữ**, có `language` đã kiểm chứng |
| `GET /categories` | `edit_posts` | category kèm ngôn ngữ (đối chiếu `term_is_vi` và termmeta `_rbhvi_lang`) |
| `GET /posts/by-key/{key}` | `edit_posts` + `edit_post` | đọc lại bài do factory tạo theo khóa idempotency (kể cả bản nháp, thùng rác) |
| `POST /posts` | `publish_posts` | tạo duy nhất, xem bên dưới |

`contract.json` trong thư mục plugin là bản máy đọc được; test đối chiếu nó với
`src/thuha/adapter.py` và với các route PHP đăng ký thật.

### Luồng `POST /posts`

1. Xác thực (chỉ Application Password; phiên cookie và `Origin` của trình duyệt bị từ chối).
2. Kiểm tra schema đóng: chỉ 11 trường, không nhận `post_status`, `post_type`, meta,
   taxonomy hay author; HTML nguy hiểm (`script`, `iframe`, `form`, `meta`, `link`,
   `style`, `on*=`, `javascript:`) bị từ chối; nội dung phải kết thúc bằng đúng một
   marker `<!-- thuha:v5 topic=… sha256=… -->`.
3. Idempotency: cùng khóa + cùng payload → trả `200 idempotent_replay` và **không đổi gì**;
   cùng khóa khác payload → `409`; cùng topic khác khóa → `409`.
4. Category và toàn bộ tổ tiên phải cùng ngôn ngữ với bài; slug phải còn trống (slug bài
   dùng chung một không gian giữa EN và VI nên slug VI không được trùng slug EN hay trang).
5. Tạo **bản nháp** đã mang marker sở hữu/idempotency.
6. `RBHVI_Language::set_vi($id, true)` (chỉ bài Việt), rồi kiểm tra cả `is_vi` lẫn
   taxonomy `rbhvi_language`. Bài EN phải không có dấu nào.
7. Ghi Yoast (`_yoast_wpseo_title/metadesc/focuskw`), ảnh đại diện, category; đọc lại từng thứ.
8. Chỉ khi slug cuối cùng vẫn đúng mới xuất bản; sau đó kiểm tra permalink nằm đúng
   không gian (`/vi/…` cho VI, gốc cho EN). Sai thì **trả về nháp**.

Lỗi sau bước 5 để lại bản nháp, không bao giờ để lại bài đang chạy ở URL sai. Python
không POST lại sau kết quả không rõ: nó đối chiếu bằng khóa (`reconcile`) và chỉ ghi
biên nhận khi đọc lại đủ (chủ sở hữu, marker, ID/URL/slug, ngôn ngữ, hai dấu native,
category, ảnh, thân bài, SEO, canonical, `<html lang>`, không có hreflang lạ, schema).

## Đã bảo đảm gì, bằng cách nào

| Yêu cầu | Cách kiểm tra offline |
|---|---|
| Không route công khai | test PHP: mọi route có `permission_callback` không phải `__return_true`; quét tĩnh cấm `__return_true`/`nopriv` |
| Không SQL, không chạy mã tùy ý | quét tĩnh `package.scan()`: `$wpdb`, `eval`, `exec`, include động, `unserialize`, HTTP ra ngoài, ghi file |
| Thiếu quyền / sai xác thực / sai origin | test PHP: 401, cookie, contributor, Origin lạ |
| Sai ngôn ngữ category | test PHP: VI vào category EN, EN vào category VI, con VI dưới cha EN |
| Chỉ category VI không đủ | test PHP: `set_vi` lỗi → bài ở lại bản nháp, không từng xuất bản |
| Gắn VI trước publish | test PHP: thứ tự `insert(draft) → set_vi → publish` |
| Replay không tạo thêm | test PHP: 200 replay, đúng một bài, đảo thứ tự khóa JSON vẫn cùng payload |
| Không đếm nháp/unknown là bài | test Python: `NEEDS_RECONCILIATION` không thành biên nhận |
| Inventory đầy đủ hai ngôn ngữ | test PHP: lọc ẩn bài VI → `thuha_inventory_filtered`, không trả danh sách thiếu |
| ZIP tái lập được | `python3 scripts/build_adapter_zip.py`; test so từng byte với ZIP đã commit |

## Giả định chưa kiểm chứng (đây là chỗ rủi ro thật)

- Chữ ký `RBHVI_Language::set_vi($post_id, true)`, `is_vi($post_id)`, `term_is_vi($term_id)`
  lấy từ `HANDOFF.md`; mã nguồn plugin native không có trong repo. `/preflight` báo
  `is_callable` của từng hàm và plugin còn đối chiếu hai dấu độc lập (hàm và taxonomy
  `rbhvi_language`, termmeta `_rbhvi_lang`); bất đồng được báo là `conflict` chứ không bị bỏ qua.
- Phiên bản PHP tối thiểu 7.4 được viết theo cú pháp tương thích nhưng chỉ chạy thử trên PHP 8.3.
- Hành vi thật của `wp_unique_post_slug`, kses, permalink `/vi/` và bộ lọc truy vấn của plugin
  native chưa được xem trên website thật; mô phỏng chỉ là bản thay thế.
- `/inventory` đối chiếu số lượng với `wp_count_posts` để phát hiện bộ lọc ẩn bài; nếu bộ lọc
  native chặn cả hai, lỗi sẽ không hiện. Cần một lần so sánh với đếm tay trên WP-Admin.

## Việc live còn lại (PENDING, do publisher có quyền làm)

1. Cài ZIP và chạy `adapter-preflight`.
2. So số bài đã xuất bản theo ngôn ngữ trong `/inventory` với màn hình bài viết của WordPress
   (kỳ vọng 275 EN, 0 VI tại thời điểm snapshot).
3. Tạo một bài thử trong môi trường staging (không dùng website thật để thử) và xác nhận URL
   `/vi/…`, hai dấu native, sitemap, `<html lang="vi">`, canonical, Yoast.
4. Kiểm tra archive category cha/con, phân trang và sitemap sau bài đầu tiên.
