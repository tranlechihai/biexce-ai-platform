# Hướng dẫn nhanh điều khiển BIEXCE

Sau khi installer chạy thành công, mở terminal mới. Windows, Ubuntu/Linux và
macOS đều dùng cùng command `biexce` từ mọi folder.

## Thiết lập lần đầu trên một máy

Kết nối provider bằng `/connect` trong OpenCode. Xem model bằng `/models`
hoặc:

```text
biexce model list
```

Danh sách này tách riêng model thấy trong catalog, trạng thái credential của
provider và trạng thái inference. Model xuất hiện trong catalog không đồng nghĩa
provider đã đăng nhập hoặc inference đã chạy thành công.

Model ID phải đúng dạng `provider/model`. Gắn model cho 7 agent:

```text
biexce setup
```

Kiểm tra:

```text
biexce status
biexce model validate
biexce self-test
```

`status` cần hiển thị `Routing: READY (7/7 agents)` và
`Runtime guard: READY`. Nếu provider báo `NOT AUTHENTICATED`, dùng `/connect`
trong OpenCode rồi chạy lại kiểm tra. Cảnh báo này không chặn user chọn hoặc
apply model. `self-test --live-inference` mới gửi request inference thật.
Restart OpenCode sau khi thay đổi model routing.

Provider `biexce-local` đọc endpoint từ `BIEXCE_LOCAL_BASE_URL`. Khi Bifrost
bắt buộc Virtual Key, cấu hình thêm `BIEXCE_LOCAL_VIRTUAL_KEY`; runtime tự gửi
header `x-bf-vk` nhưng không ghi key vào output. Restart OpenCode/OpenChamber
sau khi đổi một trong hai biến. HTTP 401/403 là lỗi key/quyền; HTTP
502/503/504 nghĩa là gateway đã tới được nhưng Bifrost/vLLM upstream đang tắt,
restart hoặc đổi model. Không thay key chỉ vì gặp 502.

## Bật và tắt Auto cho project hiện tại

Mở terminal tại folder project:

```text
biexce auto on
```

`auto on` dùng folder hiện tại làm project root, kiểm tra runtime/model, chuyển
`OFF → ON_IDLE → ARMED → RUNNING` và khởi tạo workflow ở `EXPLORE`. Nếu
project đã có workflow chưa hoàn tất, lệnh tiếp tục từ state hiện có.

Sau đó mở cùng folder bằng OpenCode, chọn `Bx-Director` và gửi mục tiêu,
constraints, definition of done. Tắt Auto:

```text
biexce auto off
```

State và artifact được giữ trong `.biexce/` của project để kiểm tra hoặc tiếp
tục về sau.

## Human Gate trong OpenCode

Workflow bắt buộc:

```text
EXPLORE → PLAN → PLAN_REVIEW → WAITING_GATE_1
  → CODE → TEST ─FAIL→ FIX → TEST
                └PASS→ TASK_REVIEW ─CHANGES REQUIRED→ FIX
                                    └APPROVE→ task kế tiếp
  → INTEGRATION_TEST ─FAIL→ INTEGRATION_FIX → INTEGRATION_TEST
                     └PASS→ INTEGRATION_REVIEW ─CHANGES REQUIRED→ INTEGRATION_FIX
                                              └APPROVE→ WAITING_GATE_2 → COMPLETE
```

Khi đến `WAITING_GATE_1` hoặc `WAITING_GATE_2`, Director gọi control tool và
OpenCode hiển thị yêu cầu xác nhận ngay trong OpenChamber hoặc TUI:

- Approve: Gate được ghi nhận và Director tự tiếp tục bước kế tiếp.
- Reject: workflow giữ nguyên ở Gate; không có state approval nào được ghi.
- Gate 2 được approve: workflow chuyển `COMPLETE` và Auto tự về `OFF`.

Mỗi child agent ưu tiên gửi kết quả qua `biexce_submit_result`. Runtime tự điền
metadata báo cáo không nhạy cảm còn thiếu và bỏ qua field phụ, nhưng vẫn từ
chối job identity cũ/sai, PASS thiếu evidence và file thuộc vùng bảo vệ. Nếu
model kết thúc mà không gọi tool này, runtime tự hoàn tất từ artifact,
filesystem diff và evidence của `biexce_run_command`; agent không còn phải tự
quản lifecycle job.
Kết quả chat dùng dòng dự phòng chính xác `BIEXCE_STATUS: <status>` cho các pha
Review. TEST chỉ được tự kết luận PASS khi có managed-command evidence exit 0.
Trong Autopilot, quyền edit của Code/Fix được runtime duyệt tự động. Ở profile
`standard`/`fast`, worker có thể thêm file source hợp lệ trong project khi Plan
không dự đoán đủ; path thuộc task song song, `.biexce`, Git, secret/credential
hoặc ngoài project vẫn bị từ chối. Profile `critical` yêu cầu toàn bộ path nằm
trong write scope đã duyệt. Director và Plan vẫn chỉ ghi artifact đúng vai.
Runtime tự quản các chi tiết điều khiển không mang tính chuyên môn: suy ra
`Project ID` ổn định khi Brief thiếu trường này, tạo `.biexce/reports`, chuẩn
hóa control block/Human Gates của Master Plan và chấp nhận DAG dạng bảng hoặc
danh sách. Thiếu metadata máy móc không còn làm terminal-fail một kế hoạch hợp
lệ; dependency sai, protected boundary hoặc evidence giả vẫn fail-closed.
Human approval vẫn bắt buộc riêng cho Gate 1 và Gate 2.
Kết quả đến trễ không thể ghi đè job đã hoàn tất. PASS khai báo thiếu exit code
bị từ chối; khi không có evidence, runtime chuyển TEST thành `INCONCLUSIVE`.
Lần đầu được retry tự động, không tiêu thụ fix round. Trong `standard`/`fast`,
lỗi kỹ thuật lặp lại chuyển workflow sang `PAUSED` thay vì khóa project; lượt
Director sau tiếp tục từ state bền vững. Sai evidence, thay đổi control-plane,
secret, path ngoài project hoặc xung đột task vẫn fail-closed.
Nếu specialist không thể hoàn tất phần việc được giao, kết quả phải là
`FAILED` kèm ít nhất một failed check. Runtime ghi nhận job thất bại, retry có
giới hạn và giữ state ở `PAUSED` nếu đó là lỗi vận hành; không cho phép báo
`SUCCEEDED` khi artifact chưa tồn tại.

Riêng `FAILED` ở phase CODE/FIX có deterministic failed check là source evidence,
không phải lỗi runtime. Scheduler đóng job hiện tại và chuyển sang BX Fix với
fix round tăng một; cùng job BX Code không được phát lại. Trong `standard`/`fast`,
BX Fix có repair authority giới hạn để cập nhật expectation cũ bị acceptance mới
thay thế, nhưng phải giữ coverage tương đương và không được xóa/skip/disable test.
`.biexce`, Git, secret/credential, path ngoài project và path của task song song
vẫn bị chặn. `critical` tiếp tục dùng exact approved write scope.

Project bị runtime cũ terminal-block sau khi đã xác thực structured `FAILED` được
migrate tự động: metadata `COMPLETED + result_status=FAILED` chuyển sang FIX có
giới hạn khi lượt drive hiện tại chọn `standard`/`fast`. Profile được áp trước
reconciliation nên explicit downgrade có hiệu lực ngay trong cùng lượt; không
cần sửa state thủ công. Migration không áp dụng nếu thiếu evidence, chạm vùng
bảo vệ. Khi đã hết fix cap, profile `standard`/`fast` chỉ tự mở đúng một vòng
adjudication cuối nếu có bằng chứng lỗi từ Test/Review; audit marker ngăn runtime
lặp vô hạn. Profile `critical` vẫn fail-closed.

Với blocker lịch sử do file source/test thông thường nằm ngoài danh sách Plan,
runtime không tin ngay kết quả cũ và cũng không phát lại cùng CODE job. Nó đọc
bằng chứng từ task cùng job history, ghi event `RUNTIME_TASK_RECOVERED`, rồi
định tuyến `TEST → FIX → TEST` khi check thật thất bại. Nếu check PASS, task đi
thẳng sang Review. Plan/Review/Test vẫn read-only; `.biexce`, Git,
secret/credential, path ngoài project và xung đột writer vẫn là hard boundary.

Ở `TEST` và `INTEGRATION_TEST`, runtime yêu cầu `Bx-Test` xác định lệnh từ tài
liệu/script của project hoặc deterministic command catalog của BIEXCE, rồi
chạy các bước áp dụng theo thứ tự:
format check, lint/static analysis, typecheck, unit/focused test,
integration/contract/E2E và build/package. Với project greenfield khai báo
Python standard-library `unittest`, catalog dùng
`python -m unittest discover -s tests -v`. Không được tự đoán framework chỉ từ
tên file. Bước không
tồn tại được ghi `N/A` kèm lý do; bước bắt buộc nhưng không thể chạy phải trả
`INCONCLUSIVE` với check `NOT_RUN`. `PASS` cần check thành công có exit code 0;
`FAIL` cần ít nhất một failed check. Runtime từ chối verdict thiếu evidence.

Mỗi task phải có dòng `Verify` là một lệnh thực thi được; Gate 1 từ chối
`Verify: N/A`. Preflight còn kiểm tra dependency/DAG, executable trong
toolchain và writable scope; scope toàn repo, state, Git hoặc secret bị từ
chối. Báo cáo được ghi ở `.biexce/reports/PREFLIGHT_REPORT.md`. Runtime cũ từng
block `INCONCLUSIVE` chỉ vì story thiếu lệnh
`unittest` sẽ tự phục hồi về TEST khi test file thực sự tồn tại. Blocker môi
trường hoặc source thật không được tự bỏ qua.

User không phải chạy lệnh approve trong terminal. Sau khi Director hoàn tất
Project Brief, `biexce_drive` tự điều phối Explore, Plan và Plan Review đến
Gate 1; sau approval, gọi lại driver để chạy task DAG đến Gate 2. Gate 1 vẫn
kiểm tra Brief, Plan, task contract, DAG, WIP 1–4, permissions, routing và
preflight trước khi cho phép code.

`PLAN_REVIEW` luôn read-only. Runtime chuẩn hóa metadata của Master Plan trước
khi vào review và không ghi lại Plan trong precondition của reviewer. Nếu một
turn Director trùng hoặc phiên cũ làm managed plan artifact thay đổi đúng lúc
review đang lấy baseline, runtime tự tạo baseline mới và chạy lại Plan Review
tối đa hai lần; recovery được ghi tại
`.biexce/state/AUTOPILOT_RECOVERY.jsonl`. Cơ chế này chỉ áp dụng cho
`MASTER_PLAN.md`, task contract và preflight do runtime quản lý. Thay đổi source
hoặc file ngoài scope vẫn giữ `BLOCKED`.

## Khôi phục task bị chặn ở trần fix

Sau ba vòng fix không đạt, BIEXCE dừng ở `BLOCKED`; không có vòng thứ tư tự
động. Nếu người dùng duyệt một bản sửa giới hạn, mở lại đúng task hiện tại:

```text
biexce autopilot resolve --project <project-path> --action manual-fix --reason "<phạm vi sửa đã duyệt>"
```

Lệnh chỉ hợp lệ khi Auto đang `RUNNING`, Gate 1 đã duyệt, blocker đúng là do
fix cap và không còn delegation lock. CLI không tự chuyển workflow; nó ghi một
runtime command gắn với revision hiện tại. Runtime xác thực rồi chuyển đúng
`BLOCKED → FIX`, giữ round 3 và ghi audit tại
`.biexce/state/AUTOPILOT_RECOVERY.jsonl`. Sau bản sửa, task vẫn phải qua bx-test
và bx-review; thất bại tiếp sẽ block lại. Không xóa lock, sửa file state hoặc
đánh dấu task done thủ công.

Không khởi động OpenCode bằng `--auto`: chế độ đó tự duyệt các permission đang
ở trạng thái ask. BIEXCE Auto là `biexce auto on` và độc lập với auto-approve
của OpenCode.

## Lệnh kiểm tra và điều khiển phụ

```text
biexce auto status
biexce auto check
biexce auto pause
biexce status
biexce self-test
```

- `auto status`: xem mode, workflow và các scheduler job đang chạy/sẵn sàng.
- `auto check`: kiểm tra đầy đủ project artifacts và runtime.
- `auto pause`: giữ state nhưng chặn delegation mới.
- `self-test`: test offline control plane và tự xóa fixture tạm.
- `self-test --live-inference`: kiểm tra thêm model thật khi đã có VPN.

Dùng `--project <path>` chỉ khi muốn điều khiển một project khác folder hiện
tại.

## Timeout và dừng an toàn

Child agent và command kiểm chứng trong Autopilot được runtime supervisor quản
lý. Timeout, nút cancel trong OpenCode hoặc `biexce auto off` sẽ abort child,
dọn process/lease và ghi trạng thái `TIMED_OUT` hoặc `CANCELLED`. User không
cần kill process, xóa lock hoặc sửa JSON state. Development server chạy vô hạn
bị chặn; dùng TestClient hoặc Playwright `webServer` do test runner quản lý.

## Retry, fallback và tiếp tục session

Runtime tự phân loại lỗi model/session. Lỗi transport, rate limit hoặc overload
được retry có giới hạn trên cùng child session; mặc định một lần với backoff.
Lỗi model unavailable hoặc context overflow có thể chuyển sang fallback tiếp
theo đã được user cấu hình. Kết quả `FAIL` của source/test không bị xem là lỗi
transport, không bị retry ẩn và vẫn đi qua vòng `FIX` theo workflow.

Lỗi schema/evidence được retry có giới hạn trong profile thường; profile
`critical` giữ contract terminal. `changed_files` và `artifacts` do model khai
chỉ là gợi ý, runtime chuẩn hóa theo filesystem thực. Standard cho phép Code/Fix
mở rộng sang file source hợp lệ trong project, nhưng `.biexce/**`, `.git/**`,
secret/credential, path ngoài project và path thuộc worker song song luôn bị
chặn cứng.

Artifact do toolchain tự sinh như `__pycache__/`, `*.pyc`, `.pytest_cache/`,
`.mypy_cache/`, `.ruff_cache/` và `.coverage*` không được tính là source diff.
Managed Python command cũng đặt `PYTHONDONTWRITEBYTECODE=1`. Nếu project cũ từng
bị block chỉ vì các artifact này sau khi CODE đã thành công, driver tự phục hồi
đúng task về `TEST`; path được bảo vệ, ngoài project hoặc thuộc task song song
vẫn bị chặn. File source phát sinh hợp lệ được nhận ở profile thường.
Mỗi phase CODE, TEST, FIX và TASK_REVIEW có Job ID/session riêng để trạng thái và
evidence của agent sau không ghi đè agent trước.

Primary model vẫn do user chọn tự do cho từng agent. Fallback khác data-zone chỉ
được runtime dùng khi user đã xác nhận `--confirm-cross-zone`; nếu chưa xác
nhận, dữ liệu local-only không bị gửi sang cloud. Actual model, số attempt và
fallback status được ghi trong job metadata.

Nếu user chủ động apply cloud binding cho `bx-review`, binding đó opt-in cho
Review đọc raw scoped diff và source tối thiểu liên quan ở `TASK_REVIEW` và
`INTEGRATION_REVIEW`. Runtime không mở ngoại lệ cho `PLAN_REVIEW`, Director,
Plan hay agent khác. Review vẫn read-only; Zone C và external directory luôn
bị deny.

Session được lưu tại `.biexce/state/AUTOPILOT_SESSIONS.json`. Nếu OpenCode hoặc
plugin khởi tạo lại giữa một lỗi transport có thể phục hồi, lần delegate kế
tiếp resume đúng child session thay vì tạo session mới. User không cần xóa lock
hoặc sửa state JSON.

## OpenChamber và OpenCode TUI

- OpenChamber: mở project, chọn `Bx-Director` trong agent selector và gửi yêu cầu.
- TUI: mở `opencode` tại project, nhấn `Tab` để chọn `Bx-Director`.
- Composer/response hiển thị agent và model đang chạy.
- Daily Assist vẫn dùng bình thường khi Auto là `OFF`; delegation đa-agent chỉ
  được mở khi project ở `RUNNING`.

Mỗi project có state riêng. Runtime dùng job board bền vững và lease riêng cho
từng job để ngăn hai cửa sổ cùng nhận một job. Scheduler đọc DAG và WIP từ
plan (1–4), giới hạn model local/cloud và chạy task trong các OpenCode child
session riêng. Vì hiện dùng chung một working tree, scheduler chỉ chạy một
`CODE/FIX` writer tại một thời điểm; read-only phase vẫn có thể song song.

Trong B3, Director gọi `biexce_drive` để runtime tự chạy các batch DAG-ready,
Integration Test, Integration Fix/Retest và Integration Review đến Human Gate
2, pause/off hoặc blocker thật. Runtime tự tạo `INTEGRATION_REPORT.md` và
`FINAL_REPORT.md` từ
evidence đã xác thực. `biexce_run_next` và
`biexce_start_job` chỉ còn là tool cấp thấp cho chẩn đoán/re-drive có giới hạn;
trạng thái bền vững xem qua `biexce_job_status`. Cancel/resume dùng
`biexce_cancel_job`/`biexce_resume_job` ngay trong OpenCode, không cần xóa lock
hoặc sửa JSON thủ công.

## Quan sát child agent

Mỗi lần scheduler giao việc sẽ tạo một OpenCode child session thật với title:

```text
[BX][t-NNN][PHASE] bx-agent
```

Tool metadata dùng contract `biexce-observability-v1` và chỉ chứa dữ liệu vận
hành cần thiết: parent/child session, job, agent, task, phase, configured/actual
model, attempt, retry/fallback, dependency, trạng thái và evidence reference.
Prompt, tool input nhạy cảm và nội dung lỗi thô không được sao chép vào metadata
quan sát.

Token, cost và duration chỉ được ghi khi OpenCode/provider trả số liệu thật.
Không có số liệu thì trường đó để unavailable; runtime không giả định bằng 0.

OpenChamber có thể được dùng như giao diện tùy chọn trên cùng OpenCode server để
xem các session này. OpenChamber không được cài mặc định, không sở hữu workflow
state và không bắt buộc để OpenCode TUI hoạt động.

### OpenChamber Desktop (khuyến nghị)

Cài ứng dụng Desktop độc lập từ trang phát hành chính thức của OpenChamber, sau
đó mở folder dự án trong ứng dụng. Bản Desktop dùng cấu hình OpenCode và bộ agent
BIEXCE đã cài theo user; không cần chạy lệnh `openchamber` hoặc tự mở trình duyệt.
VPN, `BIEXCE_LOCAL_BASE_URL`, `BIEXCE_LOCAL_VIRTUAL_KEY` và model routing vẫn
được cấu hình theo từng user/máy như khi dùng TUI. BIEXCE không tự cài hoặc tự
cập nhật OpenChamber.

### Chạy OpenChamber thủ công

Nếu đã cài OpenChamber CLI, cách đơn giản nhất trên Windows là mở PowerShell tại
project rồi chạy:

```powershell
cd D:\path\to\project
openchamber --ui-password "replace-with-a-strong-local-password"
```

OpenChamber tự khởi động và quản lý OpenCode server nền, sau đó in URL giao diện
(thường là `http://127.0.0.1:3000`). Terminal không cần giữ mở. Kiểm tra và dừng:

```powershell
openchamber status
openchamber logs
openchamber stop
```

Nếu cần OpenChamber và TUI dùng đúng một OpenCode server bên ngoài, chạy hai
terminal:

Terminal 1:

```powershell
cd D:\path\to\project
opencode serve --port 4096
```

Terminal 2:

```powershell
$env:OPENCODE_HOST = "http://127.0.0.1:4096"
$env:OPENCODE_SKIP_START = "true"
openchamber --port 43100 --ui-password "replace-with-a-strong-local-password"
```

Mở URL OpenChamber in ra. Dùng `Ctrl+C` để dừng `opencode serve` nếu chạy theo
cách hai. Có thể dùng `openchamber startup enable` để tự chạy lúc đăng nhập,
nhưng thao tác này tạo user service và chỉ thực hiện khi người dùng chủ động
chọn. Mặc định giữ bind ở `127.0.0.1`; không bind `0.0.0.0` nếu chưa có network
policy và mật khẩu phù hợp. Hướng dẫn cập nhật nằm tại
[OpenChamber OpenCode Server](https://docs.openchamber.dev/opencode-server/).

Trong OpenChamber, child agent là dòng lùi vào dưới session parent của BX
Director. Nếu parent đang thu gọn, mở mũi tên trước parent rồi chọn dòng
`[BX][t-NNN][PHASE] bx-agent` để xem đúng hội thoại specialist. Khung chat parent
vẫn ghi BX Director vì đó là coordinator; child chạy trong session riêng chứ
không thay nhãn của parent. OpenCode phát native `session.created` ngay khi
runtime tạo child, không cần dashboard hoặc state store phụ.

Khi dừng child bằng Stop/Cancel của OpenCode/OpenChamber, runtime phân loại job
là `CANCELLED`, trả task về `READY` theo policy và giải phóng WIP/lease. Không
xóa lock hoặc sửa `.biexce/state/*.json` thủ công.

Workflow profile không phải model profile. `auto` chọn `standard` mặc định;
auth/security/migration/payment/dữ liệu nhạy cảm làm tăng risk flags và yêu cầu
test/review tương ứng nhưng không tự chuyển profile. Chỉ production hoặc thao
tác destructive tự nâng lên `critical`. `fast` dành cho việc nhỏ; `advisory`
cấm sửa source. `biexce status` hiển thị effective profile và driver status.

### Nếu child báo quyền Apply Patch bị từ chối

Trong Autopilot, user không phải duyệt từng file của BX Code/BX Fix. Hai role
này được phép dùng editor. Runtime cho phép source path hợp lệ ở profile thường
và giữ deny cho state/Git/secret/outside-project/concurrent-owner; `critical`
kiểm tra đúng `write_scope` trước khi tool chạy. Human chỉ duyệt Gate 1, Gate 2
hoặc quyết định source thật sự
đã chạm fix cap. Nếu OpenChamber vẫn hiện `The user rejected permission to use
this specific tool call`, process đang giữ config/plugin cũ: đóng hoàn toàn
OpenChamber/OpenCode, cài lại và mở lại. Không sửa `PROJECT_STATE.json`, không
xóa lock và không chuyển task thủ công để né lỗi permission.

### Evidence giữa Test, Review và Fix

Runtime ghi mỗi kết quả specialist vào `AUTOPILOT_EVENTS.jsonl` dưới event
`JOB_RESULT_RECORDED`. Job sau nhận phần
`RUNTIME-AUTHORITATIVE PRIOR TASK EVIDENCE`: BX Review nhận command/exit code
của BX Test; BX Fix nhận cả failed check lẫn finding `CHANGES_REQUIRED`. Agent
không được yêu cầu user copy lại report giữa các cửa sổ chat. Blocker legacy do
thiếu handoff evidence được tự đưa về TEST để tạo lại evidence, không tiêu hao
thêm một fix round và không cần sửa state bằng tay.
