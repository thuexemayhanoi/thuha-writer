# Trạng thái triển khai: workflow 500 VI + 500 EN

Nhánh làm việc: `feature/bilingual-500-workflow` (tách từ `brief/bilingual-500-taxonomy`, **không** từ `main` cũ; ngày 23/10 đã gộp thêm nhánh phiên V5).
Không có pull request nào được tạo; `main` không bị đụng; production publisher **vẫn tắt**.

## Phiên 23/10/2026 (lần 3): vận hành workflow và viết bài thật

**Tình trạng thật, tính theo sổ cái** (`python3 -m thuha.cli --git-branch cycle`; số đã xuất bản lấy từ ảnh chụp ngày 22/10, không phải bộ đếm sống):

| | VI | EN |
|---|---|---|
| Đã xuất bản trên site (ảnh chụp 22/10) | 0 | 275 |
| Bản thảo đã lưu trong sổ cái | **7** `WAITING_DATA` (đã gộp từ 17) + 11 chủ đề `HELD` (bản đã lưu giữ nguyên) | 9 (từ phiên V5, giữ nguyên) |
| Đã có review độc lập ghi trong sổ cái | 0 | 2 |
| Qua QA | **0** | 2 (QA chạy trên inventory cũ, phải chạy lại với inventory mới) |
| Chờ review | 7 chưa thể (còn thiếu ảnh/liên kết/inventory) | 7 |
| Chờ dữ liệu (ảnh alt tiếng Việt, liên kết nội bộ đã sống, inventory adapter) | 7 | 0 |
| Biên nhận xuất bản | 0 | 0 |

Còn thiếu để đạt 500: VI 500, EN 225 (57 chủ đề EN đã vào sổ cái, trong đó 9 có bản thảo). Ma trận không phải bài viết, bản thảo không phải bài đã đăng.

**Việc đã làm.** (1) Thêm cơ chế lưu bản thảo chờ dữ liệu (`WAITING_DATA`, `submit --waiting-for`, `recheck-data`, `claim --revise`, `hold`/`unhold`, xuất `drafts/`), bằng chứng
first-party có nhãn, inventory dùng cho lập kế hoạch (ảnh chụp tối đa 7 ngày, QA vẫn 6 giờ), tất cả có test trước. (2) Viết 18 bản thảo VI từ thông tin chủ cửa hàng cung cấp, mỗi chủ đề qua kiểm
ý định độc lập (3 trong 20 bị loại vì trùng ý), mỗi bản qua precheck (không lỗi nội dung; chỉ còn ba mục chờ dữ liệu) và qua review biên tập độc lập hai lần. Lần đầu tìm ra 2 lỗi số học và nhiều chỗ lặp/giọng văn trong chính bản thảo của tôi;
lần hai khuyên xuất bản 7 trang thay vì 17 (cùng một khung, chồng lấn ý). Tôi gộp còn **7 bản** và giữ 11 chủ đề ở `HELD`. Chi tiết: [WRITING-LOG.md](WRITING-LOG.md).

**Việc chưa làm được và vì sao (nói thẳng).**
- *Không có nguồn ngoài nào được xác minh.* Từ container này chỉ `api.github.com` tới được; WebFetch không phân giải được tên miền, Firecrawl hết tín dụng, WebSearch chỉ trả tóm tắt (không phải bằng chứng). Nên mọi
  chủ đề cần luật, nhà sản xuất, địa điểm, giao thông, thời tiết vẫn là `NEEDS_SOURCE`; bảy bản EN còn lại vẫn cần reviewer mở nguồn thật.
- *Không viết tiếp hàng loạt bài "hỏi cửa hàng".* Review biên tập chỉ ra các bài cùng một khung và chỉ là danh sách câu hỏi vì chủ cửa hàng chưa trả lời chúng; thêm vài chục bài cùng khung sẽ giống nội dung sản xuất hàng loạt.
  Việc mở khóa là [những câu chỉ chủ cửa hàng trả lời được](OWNER-QUESTIONS.md).
- *Không bản nào đủ điều kiện vào hàng đợi xuất bản.* Cần: ảnh có alt tiếng Việt trong thư viện media, trang/bài tiếng Việt đã sống để liên kết, inventory từ adapter (kiểm tra thực), rồi review độc lập và QA.

**Việc phải xin quyết định của chủ cửa hàng:** (a) giọng văn thống nhất cho cả loạt bài (nay là trung tính, "giá tham khảo của Thuê xe máy Nguyễn Hà", "mỗi cửa hàng có cách làm riêng"); (b) câu trả lời cho
[10 câu hỏi](OWNER-QUESTIONS.md); (c) ảnh có alt tiếng Việt.

**Tiếp tục ở phiên sau.** `git fetch && git checkout feature/bilingual-500-workflow`; `export PYTHONPATH=src`; `python3 -m thuha.cli --git-branch cycle`; `python3 -m thuha.cli --git-branch recheck-data` (cần inventory authoritative);
`python3 -m thuha.cli --git-branch claim --session S --agent-id A --revise TH-VI-0004` để sửa bản chờ; xem [drafts/INDEX.md](../../drafts/INDEX.md). Chủ đề đã kiểm ý định mà chưa viết (13 DISTINCT: 0003, 0017, 0020, 0021, 0026, 0032, 0054, 0062, 0087, 0099, 0105,
0248, 0250; 0094 trùng 0215) và hai bản nháp chưa nhập (0017, 0026) nằm ở scratchpad của phiên này, không được coi là đã lưu.

## Phiên 23/10/2026: hợp nhất V5, hàng đợi chung, publisher theo bằng chứng WordPress

Nhánh `feature/bilingual-500-workflow` đã gộp nhánh phiên V5 (`claude/thuha-writer-v5-factory-3la2u4`, 415 commit giữ nguyên lịch sử):
sổ cái phiên (57 chủ đề, 9 bản thảo, 2 review, 4 báo cáo QA, 60 sự kiện) và 277 tài liệu bất biến vẫn đúng từng byte như phiên V5 để lại.

| Hạng mục | Đã implement | Đã test local | Đã chạy với WordPress/Actions thật |
|---|---|---|---|
| Gộp V5 vào mục tiêu 500 EN + 500 VI (kit, precheck, admit, cycle theo ngôn ngữ; không còn 2.000) | có | có | không áp dụng |
| `promote`/`sync`: chuyển sổ cái phiên vào `factory-state`, chỉ fast-forward, tài liệu trước, một CAS, chạy lại không đổi gì | có | có: sổ cái V5 thật + ảnh chụp `factory-state` ngày 23/10 (FAST_FORWARD) và 24 test | **chưa**: chạy sau khi merge, bởi job `queue` |
| Publisher: PUBLISHED khi WordPress trả ID + status + permalink hợp lệ; lệch nội dung → cảnh báo chặn bài MỚI; crawl công khai là bước phụ có back-off, không chặn hàng đợi | có | có: WordPress giả lập mức HTTP | **chưa** |
| Kết quả POST không rõ: đối chiếu theo khóa ngay và mọi lần chạy, không POST lại; kết nối chưa mở = NOT_SENT; vắng mặt sau 1 giờ mới đóng | có | có (timeout, reset, 500, adapter không với tới, chạy lặp, hai publisher đồng thời) | **chưa** |
| Hàng đợi không bị một chủ đề chặn: không qua được QA → về NEEDS_REPAIR, drain đi tiếp; chặn thật khi chưa rõ kết quả | có | có | **chưa** |
| Workflow: job `queue` (không có secret WordPress) + job bảo vệ; `qa --pending`; `audit --max-age` | có | kiểm bằng đọc YAML (thứ tự, cổng) | **chưa chạy** |
| Thư viện media đầy đủ trong inventory; dashboard báo `NEEDS_MEDIA` | có | có | chưa |
| Matrix EN: 275 bảo vệ + 57 đã vào sổ cái + 168 mới; 57 dòng gỡ vì trùng chủ đề đã vào hàng đợi (giữ ở `seeds/retired/`) | có | có | chưa (dedup live còn PENDING) |
| Theme 1.4.0, plugin `rentbikehanoi-native-vi` 1.1.1 | **không đụng**, không nằm trong repo | — | — |

**Chín bản thảo.** TH-000005 và TH-000006 (có review) vượt QA lại dưới chính sách song ngữ mới; bảy bản còn lại chờ review độc lập
(TH-000002 đang bị writer giữ lease, hết hạn sẽ về hàng đợi). Tôi không tự viết review: reviewer phải mở nguồn thật.
Cả chín đã được chạy thử qua QA hiện tại (chỉ đọc, bằng inventory V5 đã lưu với nhãn ngôn ngữ danh mục suy từ URL — chưa phải QA trên inventory mới): ngoài thiếu review không có lỗi nào khác, sau khi sửa hai điểm dưới đây. QA thật chạy lại khi job `queue` có inventory mới.

**Hai lỗi của chính tôi tìm ra khi chạy bản thảo thật** (đã sửa, có test): (1) bộ lọc "tiếng Việt lẫn vào bài tiếng Anh" đếm tuyệt đối 3
từ chức năng tiếng Việt nên chặn nhầm TH-000003 (bài Anh trích tên giấy phép lái xe bằng tiếng Việt); nay ngưỡng tỷ lệ theo độ dài.
(2) Review của V5 chỉ xác nhận `english`, không có nhãn ngôn ngữ nên bị loại; nay review EN cũ vẫn hợp lệ cho EN, còn VI vẫn bắt buộc
`native_language` và `no_machine_translation`.

**Một lỗ hổng lộ ra từ việc kiểm tra media:** inventory trước đây chỉ liệt kê ảnh đại diện của bài đã có, nên một ảnh có alt tiếng Việt
chưa bài nào dùng sẽ không bao giờ xuất hiện; nay `audit` liệt kê cả thư viện. Nhưng hiện chưa có ảnh nào có alt tiếng Việt: **chưa bài VI nào qua được QA**
cho đến khi thư viện có ít nhất một ảnh như vậy (việc của người có quyền WordPress).

### Review độc lập lần hai (23/10) và cách xử lý

Một agent khác đọc phần hand-over, publisher, workflow và test, rồi chạy 54 đột biến một dòng. Mọi phát hiện đều được tôi chạy lại trước khi sửa:

| # | Phát hiện | Xử lý |
|---|---|---|
| 1 | **Hand-over chỉ chạy được một lần**: sau lần đầu, mọi lô việc sau bị báo "đã có" và bỏ rơi lặng lẽ; `sync` không chép gì | so sánh lịch sử theo nội dung từng sự kiện (bỏ qua chuỗi hash và dấu migration); test ba vòng sync → làm việc → promote |
| 2 | Intent đã đóng (`NOT_SENT`/`REJECTED`) chặn QA mãi; mã thoát của QA làm bước Drain bị bỏ qua | `run_qa` chỉ chặn intent chưa đóng; `qa --pending` báo FAIL trong sổ cái và thoát 0; bước audit/QA có `continue-on-error` |
| 3 | `pending_qa` nhận review của bản cũ | review phải đúng `article_sha` hiện tại |
| 4 | `DRAFT_HELD` không có lối ra; `reconcile` báo CLOSED mà sổ cái không đổi | bản nháp bị xóa → sau thời gian chờ intent đóng và chủ đề đăng lại được; bản nháp trong thùng rác phải xóa hẳn |
| 5 | Review không để lại sự kiện nên không bao giờ được chuyển; `continuity` quá lỏng (sổ cái phiên sửa tay có thể mở lại intent đang chờ) | `review` ghi sự kiện `REVIEW`; sổ cái phiên không được mang intent/biên nhận mà publisher không viết; kiểm tra cả biên nhận, intent, yêu cầu nghiên cứu, review |
| 6 | Một trang 404 làm audit dở dang và dừng QA/drain; `promote` bị từ chối làm các bước sau bị bỏ qua | các bước độc lập, cuối job báo đỏ nếu hand-over bị từ chối |
| 7 | `GitBranchStore`: ghi dở tài liệu không bao giờ được commit; hai clone cùng nhánh để lại file JSON đầy dấu xung đột; `sync` bỏ 24/39 tài liệu nguồn | ghi nguyên tử, commit nốt tài liệu bỏ dở, ghi sổ cái theo kiểu CAS (bỏ commit, kéo nhánh, làm lại), `referenced` đi theo nguồn trong bài |
| 8 | `publisher_lease` hết hạn chặn `promote` mãi | chỉ lease còn hạn mới chặn |
| 9 | `ENETUNREACH`/`EHOSTUNREACH` có thể đến sau khi yêu cầu đã tới nơi nhưng bị coi là "chưa gửi" | chỉ lỗi phân giải tên và bị từ chối kết nối mới là `NOT_SENT` |
| 10, 11 | `audit --max-age` coi inventory ngày mai là mới; `migrate` không đổi `VERIFIED` | `fresh()`; migrate đổi `VERIFIED` → `PUBLISHED`, `VERIFY_PENDING` → `NEEDS_RECONCILIATION` |
| 12 | `live=false` ghi là xem trước chỉ-đọc nhưng job `queue` vẫn ghi | job `queue` bỏ qua khi chạy tay không `live` |
| — | Tiêu đề test nói "hai publisher cùng lúc" nhưng không có test; nhiều guard không test nào bắt (lease, fence trước POST, rate limit, ngân sách pilot, bản nháp đổi, `quota.reserve`, `verify_security`, pilot==2, so sánh nội dung/category/Yoast, ghi biên nhận trùng, `demote`, khoảng chờ, re-plan của sync…) | thêm test cho từng guard và test chạy luồng thật hai publisher đồng thời (6 vòng); chạy lại các đột biến đó (và các kiểm tra mới của sổ cái): tất cả bị bắt |

Còn lại và nói thẳng: công việc làm trên bản sao cũ của sổ cái (khi Actions đã ghi thêm) không tự gộp được, chỉ bị từ chối; một intent
mà WordPress không bao giờ thấy chỉ được đóng sau một giờ; khoảng trống của bộ lọc ngôn ngữ cho văn bản rất ngắn đã được vá riêng cho alt text.

### Việc phải thiết lập một lần để chạy tự động (không làm được và không kiểm được offline)

1. Review và merge nhánh này → quality chạy → job `queue` chuyển chín bản thảo vào `factory-state`.
2. Bảo vệ nhánh: `main` cần 1 review + check `quality`; `factory-state` chỉ app GitHub Actions được ghi, cấm force push.
3. Environment `thuha-production` có người duyệt, secrets `THUHA_WP_USER`, `THUHA_WP_APPLICATION_PASSWORD`, `THUHA_GITHUB_SECURITY_TOKEN`, biến `THUHA_GO_LIVE_APPROVAL`.
4. Cài `dist/thuha-native-vi-publisher-1.0.0.zip`, chạy `adapter-preflight` (người/AI có quyền WordPress xem trước và triển khai).
5. Thêm ảnh có alt tiếng Việt vào thư viện media.
6. Review độc lập bảy bản thảo EN (và các bản VI khi có). Danh tính reviewer chỉ là chuỗi tự khai (`claude-editorial-reviewer` trong `config/qa.json`), không phải xác thực: chủ sở hữu xác nhận hoặc thay roster và bảo vệ quyền ghi sổ cái trước khi tin cho production.
7. Quyết định go-live: một thay đổi `config/release.json` đã được review (`enabled`, `approved`, `approval_ref`, `paused:false`, `cross_publisher_coordination_verified`, `languages_enabled`). Giai đoạn đầu tối đa 2 bài.

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
| Matrix VI500 (500 mới) và EN500 (275 bảo vệ + 57 đã vào sổ cái + 168 mới) | có | có (validator, chống trùng, URL/category, khớp sổ cái) | không áp dụng | chưa: dedup live và dedup với 11 trang tĩnh VI cần inventory live |
| Nguồn nghiên cứu, review ý định, viết bài, review độc lập | **EN: do phiên V5 làm** (57 chủ đề có nguồn đã chụp, 9 bản thảo, 2 review); **VI: chưa làm** | không áp dụng | không áp dụng | không áp dụng |

**Chưa có bài nào được xuất bản bởi factory.** Có 9 bản thảo tiếng Anh (từ phiên V5) trong sổ cái, 2 bản có review; chưa có bản thảo tiếng Việt.
Các dòng matrix là kế hoạch, mọi dòng mới ở `NEEDS_SOURCE`: không có nguồn nào được thu thập cho chúng (không có kết nối WordPress/crawler
trong phiên này và không được bịa), chưa đo nhu cầu tìm kiếm (`demand_evidence: NOT_MEASURED`). Không được nói "đã có 1000 bài".

## Review độc lập và cách xử lý

Một agent khác (không biết kết luận của tôi) đọc plugin, publisher, quota, migration và HTTP, báo 15 phát hiện; tôi kiểm chứng từng cái
trước khi sửa (có cái chạy trên state `factory-state` thật và regex thật). Đã sửa và có test hồi quy (mỗi cái được thử bằng cách
phá code rồi xem test đỏ):

| # | Phát hiện | Xử lý |
|---|---|---|
| 1 | Mọi lỗi sau khi giữ chỗ đều đốt intent vĩnh viễn (không có đường hủy) | pha đóng `NOT_SENT`/`REJECTED`; kiểm payload **trước** khi giữ chỗ; mã lỗi plugin được giữ lại, không giữ nội dung phản hồi |
| 2 | Bộ lọc HTML bị lách (`<svg/onload>`, `onerror` dính liền, `&#106;avascript:`) và chặn nhầm chữ "JavaScript:" | chính sách HTML dạng chuẩn dùng chung Python/PHP + vector chung |
| 3 | Kiểm permalink sau khi publish; revert thất bại vẫn báo "đã về nháp" | kiểm trên bản sao trạng thái publish **trước**; revert được đọc lại, thất bại → `thuha_revert_failed`; tài liệu sửa lại cho đúng |
| 4 | Số đếm ngoài giao dịch CAS: bài vừa verify sau khi đọc inventory không được tính | `quota.reserve(live_ids)` cộng bài VERIFIED chưa có trong inventory |
| 5 | Trên state thật, request nghiên cứu EN treo (không có `language`) chặn mọi request VI | refill duyệt theo thứ tự ưu tiên ngôn ngữ, request EN không chặn VI |
| 6 | Thiếu `wp_slash` làm mất dấu `\`; tiêu đề/thân bài không được đọc lại | `wp_slash` mọi chuỗi; đọc lại tiêu đề + thân bài; Python so tiêu đề |
| 7 | `suppress_filters` không chặn `pre_get_posts`/`posts_pre_query` | gỡ tạm hai hook khi tra khóa/inventory (chưa thử với plugin native thật) |
| 8 | Regex `$` nhận ký tự xuống dòng; `\d` nhận chữ số Unicode | neo `D`/`fullmatch`, `[0-9]` |
| 9 | Lỗi mất phản hồi có thể ghi đè bản ghi VERIFIED | `settle` không đụng bản ghi đã VERIFIED |
| 10 | Inventory lộ thân bài của bài có mật khẩu | thân bài bị giữ lại, cờ `password_protected` |
| 11 | Hai POST đồng thời cùng khóa tạo hai nháp | khóa `add_option` nguyên tử, `thuha_in_progress` |
| 12 | Giới hạn của plugin tính theo byte, client tính theo ký tự | giới hạn byte trong `contract.json`, mirror ở `validate_payload` và `submit` |
| 13 | Inventory snapshot rơi vào KeyError khi publish | báo lỗi rõ, publish đòi inventory dạng adapter |
| 14 | Cờ Application Password tĩnh có thể sai trong worker PHP | ưu tiên hàm lõi `rest_get_authenticated_app_password()` |
| 15 | Yoast có thể làm sạch lại SEO làm hỏng đọc lại | QA từ chối khoảng trắng thừa, thẻ, nháy trong từ khóa; sai khác còn lại để bài ở nháp |

Còn lại và nói thẳng: nhà xuất bản ngoài factory có thể vượt trần giữa hai lần đếm (cần `cross_publisher_coordination_verified`);
một bài đã lên WordPress mà chưa đọc lại xong bị đếm hai lần cho tới khi `reconcile` (thiên về an toàn); mọi hành vi của WordPress,
Yoast và plugin native thật vẫn chưa được thử.

## Kiểm tra đã chạy (offline)

```
PYTHONPATH=src python3 -m unittest discover -s tests -v   # xem số test ở commit cuối bên dưới
PYTHONPATH=src python3 -m thuha.cli validate              # cấu hình, goal 500/500, matrix, gói adapter
php tests/php/run.php                                     # 25 tình huống plugin trên mô phỏng WordPress
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

### Số liệu ở điểm dừng (đo bằng lệnh ở mục "Kiểm tra đã chạy"; cập nhật 2026-10-23)

| Hạng mục | Kết quả |
|---|---|
| Python unittest | 327 test, tất cả OK (~33 giây) |
| PHP harness (mô phỏng WordPress) | 25 tình huống đạt, 0 lỗi |
| `thuha.cli validate` | PASS (goal 500/500, 2 matrix, gói adapter, chính sách QA) |
| Matrix VI500 | 500 dòng mới, 0 vấn đề |
| Matrix EN500 | 500 dòng = 275 bảo vệ + 57 đã vào sổ cái + 168 mới, 0 vấn đề |
| ZIP plugin | `dist/thuha-native-vi-publisher-1.0.0.zip`, SHA-256 `08654741d0bd3c97757b877b67d47c28a9609314b3eaf38d1135555471c3dedb` |
| Workflow YAML | đọc được (Ruby YAML) |
| Bản thảo EN trong sổ cái (9, từ phiên V5) / bài đã xuất bản bởi factory | 9 / 0 |
| `release.json` `languages_enabled` | `[]` (production vẫn tắt) |
| Trạng thái adapter | `BLOCKED_ADAPTER_NOT_DEPLOYED` (chưa cài, chưa preflight) |
| Sổ cái phiên → `factory-state` | `FAST_FORWARD` trên ảnh chụp ngày 23/10 (phiên V5 v137, shared v5); chưa chạy thật |

Commit cuối của nhánh là điểm dừng; số test có thể thay đổi nếu có commit sau mục này.

