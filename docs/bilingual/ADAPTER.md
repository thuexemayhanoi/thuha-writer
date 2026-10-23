> **Current instructions (23 Oct 2026):** `THUHA_WP_USER` and `THUHA_WP_APPLICATION_PASSWORD` belong in repository GitHub Actions Secrets, NOT GitHub Environment; current QA is **>=75 and no hard failures**. Older Environment instructions below are superseded.

# Plugin kết nối xuất bản `thuha-native-vi-publisher`

Plugin đồng hành này là **đường ghi duy nhất** của workflow vào rentbikehanoi.com.
Nó tồn tại vì ba lý do trong brief: bài Việt cần dấu `rbhvi_language=vi` gắn **trước**
khi xuất bản, REST public không đáng tin để đếm bài Việt, và `/wp/v2/posts` của core
không có trường ngôn ngữ đã kiểm chứng.

> **Trạng thái khi tài liệu triển khai ban đầu được viết (lịch sử):** plugin đã viết, đóng gói và thử trên mô phỏng WordPress. Khi đó chưa xác minh triển khai trên website. **Cập nhật 23/10/2026:** workflow publisher hiện đã chạy thành công với **9 biên nhận xuất bản EN** trong shared ledger v448; điều này **chưa tự chứng minh luồng viết VI, ảnh alt VI hay internal links VI sẵn sàng**. Mọi đánh giá trạng thái live phải đọc lại kết quả adapter preflight/inventory và WordPress receipts, không dùng đoạn lịch sử này để khóa viết bài.

## Cài đặt (làm trong giao diện WordPress, không sửa tay hosting)

1. Lấy file `dist/thuha-native-vi-publisher-1.0.0.zip` (SHA-256 nằm ở
   `dist/thuha-native-vi-publisher-1.0.0.zip.sha256`).
2. WordPress Admin → **Plugins → Add New → Upload Plugin** → chọn ZIP → **Activate**.
   Plugin `rentbikehanoi-native-vi` phải đang bật; nếu không, mọi route trừ
   `/preflight` trả `503 thuha_native_vi_missing` và có thông báo trong admin.
3. Tạo **Application Password** cho một người dùng có quyền xuất bản bài
   (Users → Profile → Application Passwords). Không dùng tài khoản quản trị chung nếu
   có thể tạo vai trò Editor riêng.
4. Chủ website (hoặc người giữ secret) đặt user và application password vào GitHub Actions **Repository Secrets** (`THUHA_WP_USER`,
   `THUHA_WP_APPLICATION_PASSWORD`). Không dán vào repo, issue, log hay prompt.
5. Publisher có thông tin xác thực chạy `python3 -m thuha.cli --remote adapter-preflight`.
   Chỉ khi lệnh này thành công, trạng thái adapter trong state mới là `VERIFIED`.
   Cho tới lúc đó dashboard báo `BLOCKED_ADAPTER_NOT_DEPLOYED`.
6. **Lịch sử:** việc bật production vốn là một quyết định riêng. Chủ website đã bật `config/release.json` vào 23/10/2026 với `auto-scale` và giới hạn 50 bài/ngày; **không bật lại, không tạo vòng phê duyệt mới**. Cần đối chiếu cấu hình và biên nhận mới nhất.

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

1. Xác thực: chỉ Application Password (ưu tiên hàm lõi `rest_get_authenticated_app_password()`, cờ nội bộ chỉ là phương án
   dự phòng); phiên cookie và `Origin` của trình duyệt bị từ chối.
2. Schema đóng: đúng 11 trường, regex neo chặt (`\z`/`D`, chữ số ASCII), giới hạn theo **byte** UTF-8 (nội dung 200000, tiêu đề 300,
   mỗi trường SEO 400, slug 90 — lấy từ `contract.json`), tiêu đề/SEO là văn bản thuần một dấu cách; nội dung phải kết thúc bằng
   đúng một marker `<!-- thuha:v5 topic=… sha256=… -->`.
3. **Chính sách HTML dạng chuẩn** (`contract.json › html_policy`, cùng thuật toán trong `src/thuha/htmlpolicy.py` và PHP): chỉ thẻ
   thường trong danh sách cho phép, thuộc tính trong dấu nháy kép, không trùng, URL chỉ ASCII in được, chỉ thực thể `&amp;`, chỉ
   scheme `http/https/mailto/tel`, không bình luận/khai báo/`<` trần. Cái gì ngoài khuôn bị từ chối chứ không được "diễn giải".
   Vector dùng chung `tests/fixtures/html-policy-vectors.json` chạy ở cả Python và PHP.
4. Khóa đồng thời (`add_option` nguyên tử) theo khóa idempotency, rồi idempotency: cùng khóa + cùng payload → `200 idempotent_replay`
   và **không đổi gì**; cùng khóa khác payload → `409`; cùng topic khác khóa → `409`; đang có yêu cầu chạy → `409 thuha_in_progress`.
5. Category và toàn bộ tổ tiên phải cùng ngôn ngữ; ảnh đại diện phải là attachment đọc được có alt; slug phải còn trống (slug bài
   dùng chung một không gian giữa EN và VI, và không trùng trang).
6. Tạo **bản nháp** mang marker sở hữu/idempotency. Mọi chuỗi đi qua `wp_slash` (lõi tự `unslash`, nếu không dấu `\` bị mất), rồi
   đọc lại tiêu đề và thân bài: khác bản đã review (ví dụ do kses) → `thuha_content_altered`, bài ở lại nháp.
7. `RBHVI_Language::set_vi($id, true)` (chỉ bài Việt), kiểm tra cả `is_vi` lẫn taxonomy `rbhvi_language`; bài EN phải không có dấu nào.
8. Ghi Yoast, ảnh đại diện, category; đọc lại từng thứ.
9. **Quyết định trước khi publish:** slug cuối vẫn đúng; permalink của một **bản sao đã đặt trạng thái publish** nằm đúng không gian
   (`/vi/…` hoặc gốc). Sai thì dừng khi bài vẫn là nháp.
10. Publish, rồi kiểm tra lại một lần như lưới an toàn. Nếu lúc này vẫn sai, bài bị trả về nháp và **được đọc lại để chắc**; nếu không
    trả về được thì trả `thuha_revert_failed` và nói rõ bài có thể ĐANG CHẠY. Hiệu ứng phụ của việc đã publish (feed, sitemap, ping)
    không thể hoàn tác bằng cách đặt lại nháp, vì vậy bước 9 mới là bước quyết định.

Lỗi sau bước 6 để lại bản nháp. Python không POST lại sau kết quả không rõ: nó đối chiếu theo khóa (`reconcile`) ngay lập tức và ở mọi lần
chạy sau. **Một bài được ghi PUBLISHED khi WordPress trả ID hợp lệ, status `publish` và permalink đúng như kế hoạch** (đúng không gian
ngôn ngữ), và bài mang đúng chủ sở hữu, khóa idempotency và marker của intent đó; ID thuộc bài đã có từ trước bị từ chối.
Sau đó (không phải trước) phần đọc lại của adapter được so với bài đã review (ngôn ngữ, hai dấu native, category, ảnh, tiêu đề, thân bài,
SEO) và kết quả `integrity` được ghi vào biên nhận; lệch → cảnh báo chặn bài MỚI cho đến khi có người `acknowledge`.
Trang công khai (canonical, tiêu đề, meta, `<html lang>`, không hreflang lạ, schema, không `noindex`) được kiểm tra **sau cùng**
như bước phụ: thử lại có back-off (10 phút, 30 phút, 1 giờ, 3 giờ), tối đa năm lần, lỗi chỉ là cảnh báo và không bao giờ chặn hàng đợi.
Bài còn là nháp ở phía WordPress (`DRAFT_HELD`) không bao giờ được tính và không bao giờ bị gửi lại.

**Đóng intent thay vì đốt vĩnh viễn.** Intent có hai pha *đóng* (không tính vào quota, ngân sách pilot hay hạn mức ngày, và topic được
đăng lại sau khi sửa): `NOT_SENT` (lỗi trước khi POST được gửi: payload không qua `validate_payload`, tạm dừng, mất quyền) và `REJECTED`
(plugin trả một mã trong `definitive_rejections_before_insert` **và** đọc lại theo khóa không thấy gì). Payload mà plugin chắc chắn từ chối
bị chặn **trước** khi giữ chỗ. Mọi trường hợp khác (timeout, 5xx, mã có thể xảy ra sau khi đã có bản nháp) vẫn là `NEEDS_RECONCILIATION`
và tiếp tục tính vào quota; một bản ghi PUBLISHED không bao giờ bị ghi đè. Kết nối chưa từng mở được (không phân giải được tên, bị từ chối,
mạng không tới được) là `NOT_SENT`; một intent mà WordPress vẫn không có sau một giờ cũng được đóng (`REJECTED`, `absent_after_grace`).

## Đã bảo đảm gì, bằng cách nào

| Yêu cầu | Cách kiểm tra offline |
|---|---|
| Không route công khai | test PHP: mọi route có `permission_callback` không phải `__return_true`; quét tĩnh cấm `__return_true`/`nopriv` |
| Không SQL, không chạy mã tùy ý | quét tĩnh `package.scan()`: `$wpdb`, `eval`, `exec`, include động, `unserialize`, HTTP ra ngoài, ghi file |
| Thiếu quyền / sai xác thực / sai origin | test PHP: 401, cookie, contributor, Origin lạ |
| Sai ngôn ngữ category | test PHP: VI vào category EN, EN vào category VI, con VI dưới cha EN |
| Chỉ category VI không đủ | test PHP: `set_vi` lỗi → bài ở lại bản nháp, không từng xuất bản |
| Gắn VI trước publish | test PHP: thứ tự `insert(draft) → set_vi → publish` |
| Permalink sai bị chặn trước publish | test PHP: bài chưa từng được publish; revert thất bại được báo `thuha_revert_failed` |
| Bộ lọc HTML không bị lách (`<svg/onload>`, `onerror` dính liền, `&#106;avascript:`) | vector chung chạy ở Python và PHP; mutation test |
| Dấu `\` và nháy trong bài còn nguyên | test PHP với mô phỏng `unslash` như lõi |
| Hai POST đồng thời cùng khóa | test PHP: khóa giữ → `thuha_in_progress`; khóa treo cũ được tiếp quản |
| Bộ lọc truy vấn của plugin native ẩn bài VI | test PHP: hook `pre_get_posts` được gỡ tạm khi tra khóa/inventory và đặt lại |
| Bài có mật khẩu không lộ thân bài trong inventory | test PHP |
| Replay không tạo thêm | test PHP: 200 replay, đúng một bài, đảo thứ tự khóa JSON vẫn cùng payload |
| Không đếm nháp/unknown là bài | test Python: `NEEDS_RECONCILIATION` và `DRAFT_HELD` không thành biên nhận |
| Lỗi crawl sau đăng không chặn hàng đợi | test Python toàn tuyến: bài kế tiếp vẫn được đăng; cảnh báo hiện trên dashboard |
| Inventory đầy đủ hai ngôn ngữ | test PHP: lọc ẩn bài VI → `thuha_inventory_filtered`, không trả danh sách thiếu |
| ZIP tái lập được | `python3 scripts/build_adapter_zip.py`; test so từng byte với ZIP đã commit |

## Giả định chưa kiểm chứng (đây là chỗ rủi ro thật)

- Chữ ký `RBHVI_Language::set_vi($post_id, true)`, `is_vi($post_id)`, `term_is_vi($term_id)`
  lấy từ `HANDOFF.md`; mã nguồn plugin native không có trong repo. `/preflight` báo
  `is_callable` của từng hàm và plugin còn đối chiếu hai dấu độc lập (hàm và taxonomy
  `rbhvi_language`, termmeta `_rbhvi_lang`); bất đồng được báo là `conflict` chứ không bị bỏ qua.
- Phiên bản PHP tối thiểu 7.4 được viết theo cú pháp tương thích nhưng chỉ chạy thử trên PHP 8.3.
- Hành vi thật của `wp_unique_post_slug`, kses, `wp_slash`/`unslash`, permalink `/vi/` và các hook truy vấn của plugin native chưa được
  xem trên website thật; mô phỏng chỉ là bản thay thế. Hook `pre_get_posts`/`posts_pre_query` được gỡ tạm khi tra khóa và inventory
  để plugin native không giấu bài VI; cách này chưa được thử với plugin native thật.
- `/inventory` đối chiếu số lượng với `wp_count_posts` để phát hiện bộ lọc ẩn bài; nếu bộ lọc native chặn cả hai, lỗi sẽ không hiện.
  Cần một lần so sánh với đếm tay trên WP-Admin.
- Tài khoản có quyền `unfiltered_html` (Editor, Administrator) bỏ qua kses, nên chính sách HTML của adapter là lớp chặn duy nhất cho nội
  dung; còn tài khoản không có quyền đó có thể bị kses sửa nội dung, khi đó `thuha_content_altered` giữ bài ở nháp.
- Yoast có thể làm sạch lại trường SEO khi lưu (ví dụ bỏ dấu nháy trong từ khóa chính). QA đã từ chối khoảng trắng thừa, thẻ HTML và
  nháy trong từ khóa, nhưng quy tắc làm sạch thật của phiên bản Yoast đang cài chưa được thấy; sai khác sẽ để bài ở nháp.
- Quota đếm hai lần một bài đã lên WordPress nhưng chưa đọc lại xong (vừa nằm trong inventory vừa là intent chưa giải quyết); đây là
  thiên về an toàn và chỉ tự hết sau khi `reconcile` thành công. Nhà xuất bản bên ngoài không thuộc factory vẫn có thể làm vượt
  trần giữa hai lần đếm: cần `cross_publisher_coordination_verified` như đã yêu cầu trong release.
- Phiên làm việc dài của PHP (worker): cờ Application Password chỉ là dự phòng; đường chính là hàm lõi.

## Việc live còn lại (PENDING, do publisher có quyền làm)

1. Cài ZIP và chạy `adapter-preflight`.
2. So số bài đã xuất bản theo ngôn ngữ trong `/inventory` với màn hình bài viết của WordPress
   (kỳ vọng 275 EN, 0 VI tại thời điểm snapshot).
3. Tạo một bài thử trong môi trường staging (không dùng website thật để thử) và xác nhận URL
   `/vi/…`, hai dấu native, sitemap, `<html lang="vi">`, canonical, Yoast.
4. Kiểm tra archive category cha/con, phân trang và sitemap sau bài đầu tiên.
