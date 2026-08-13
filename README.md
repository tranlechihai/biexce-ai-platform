# BIEXCE — Bộ agent cho OpenCode

BIEXCE AGENTS cung cấp 7 agent hỗ trợ quy trình phát triển phần mềm qua OpenCode
TUI hoặc giao diện OpenChamber Desktop/Web. Bộ cài đặt theo tài khoản người dùng
sẽ đăng ký agent, skill, model routing, runtime guard và Autopilot theo từng dự
án mà không cần quyền Administrator hoặc `sudo`.

## Các agent

| Agent | Trách nhiệm |
| --- | --- |
| `bx-director` | Điều phối workflow và các Human Gate |
| `bx-explore` | Khảo sát repository và tạo Codebase Brief |
| `bx-plan` | Lập kế hoạch và tạo task contract có phạm vi rõ ràng |
| `bx-code` | Triển khai các task đã được duyệt |
| `bx-fix` | Phân tích và sửa lỗi dựa trên evidence |
| `bx-test` | Chạy kiểm tra và cung cấp test evidence |
| `bx-review` | Review kế hoạch, thay đổi source và kết quả tích hợp |

Mỗi agent có thể dùng bất kỳ `provider/model` nào người dùng đã kết nối và lựa
chọn.

## Yêu cầu

- OpenCode 1.18.4 trở lên.
- Python 3 có trong `PATH`.
- Windows PowerShell 5.1+, hoặc `bash` trên Linux và macOS.
- Provider cloud đã kết nối nếu sử dụng model cloud.
- Có kết nối mạng tới endpoint đã cấu hình nếu sử dụng model nội bộ.

## Cài đặt

Clone repository hoặc giải nén release package, sau đó chạy bộ cài tương ứng
với hệ điều hành.

Windows:

```powershell
.\bin\windows\install.cmd
```

Ubuntu/Linux:

```bash
chmod u+rx bin/linux/*.sh
./bin/linux/install.sh
```

macOS:

```bash
chmod u+rx bin/macos/*.command
./bin/macos/install.command
```

Sau khi cài đặt, hãy mở terminal mới. Lệnh global sau đó có thể dùng tại mọi
thư mục dự án:

```text
biexce setup
biexce status
biexce self-test
```

## Cấu hình model

Dùng `/connect` và `/models` trong OpenCode, hoặc chạy `opencode models`, để
xem các model hiện có. Model ID phải đúng định dạng `provider/model`.

Kiểm tra catalog và trạng thái provider:

```text
biexce model list
```

`catalog_status: DISCOVERED` chỉ xác nhận model xuất hiện trong catalog.
`credential_status` cho biết provider đã có thông tin đăng nhập hay chưa;
`inference_status: NOT VERIFIED` nghĩa là lệnh này chưa gửi request thật.
Nếu provider báo `NOT AUTHENTICATED`, dùng `/connect` trong OpenCode. BIEXCE vẫn
cho phép user chọn và lưu model đó, nhưng sẽ cảnh báo khi setup, validate,
status và doctor.

Thiết lập tương tác:

```text
biexce setup
```

Thiết lập không tương tác với một model mặc định và model riêng cho agent nếu
cần:

```text
biexce setup --model <provider/model> --agent bx-code=<provider/model> --yes
biexce model validate
```

Ví dụ hybrid do user tự chọn, không hard-code trong source:

```text
biexce setup --model <local-provider/model> --agent bx-director=<cloud-provider/model> --agent bx-plan=<cloud-provider/model> --agent bx-review=<cloud-provider/model> --yes
```

Khi `bx-review` được gắn cloud model, binding này đồng thời là opt-in cho agent
Review đọc raw scoped diff và source tối thiểu liên quan trong các phase review
sau Gate 1. Review vẫn read-only và các file secret/credential vẫn bị deny.

Provider nội bộ tùy chọn đọc endpoint từ biến môi trường
`BIEXCE_LOCAL_BASE_URL`. Giá trị phải là OpenAI-compatible base URL kết thúc
bằng `/v1`. Nếu Bifrost bắt buộc Virtual Key, lưu key theo user/máy trong
`BIEXCE_LOCAL_VIRTUAL_KEY`; OpenCode và lệnh kiểm tra sẽ tự gửi key qua header
`x-bf-vk`. Source và file cấu hình chỉ chứa tham chiếu biến, không chứa key
thật. Hãy khởi động lại OpenCode/OpenChamber sau khi đổi endpoint, key hoặc
model routing. Kiểm tra inference thật bằng `biexce self-test --live-inference`.

## Sử dụng Autopilot

Tại thư mục dự án cần chạy:

```text
biexce auto on
```

Mở cùng thư mục bằng OpenCode, chọn `Bx-Director`, rồi cung cấp mục tiêu, ràng
buộc và definition of done. BIEXCE sẽ dừng tại Human Gate 1 trước khi triển
khai và Human Gate 2 trước khi hoàn tất. Việc duyệt được thực hiện trực tiếp
trong OpenCode TUI hoặc OpenChamber. Kết quả child agent được runtime kiểm tra
theo JSON schema, evidence và writable scope trước khi workflow chuyển bước.

Mỗi task áp dụng chuỗi kiểm tra phù hợp với project theo thứ tự: format check →
lint/static analysis → typecheck → unit/focused test → integration/contract/E2E →
build/package. `Bx-Code` viết code và test trong phạm vi task; `Bx-Test` chạy lại
độc lập và trả evidence; lỗi source đi qua `Bx-Fix` rồi quay lại `Bx-Test`. Bước
không tồn tại trong project được ghi `N/A` kèm lý do. Một bước bắt buộc nhưng
không chạy được phải trả `INCONCLUSIVE`, không được coi là PASS. Runtime tự
thử lại mà không tính vòng fix. Profile thường chuyển `PAUSED` khi hết retry để
có thể tiếp tục từ state đã lưu; profile `critical` mới block theo contract.

Sau khi Director tạo Project Brief, autonomous driver tự chạy Explore → Plan →
Plan Review và dừng tại Gate 1. Preflight trước Gate kiểm tra DAG, lệnh `Verify`,
toolchain và writable scope. Sau khi duyệt, cùng driver tự lấy các task
DAG-ready theo WIP/write scope/model quota và tiếp tục Code → Test → Fix →
Review → Integration Test → Integration Fix/Retest →
Integration Review cho đến
Human Gate 2 hoặc một blocker thật. Báo cáo tích hợp và bàn giao được runtime
tạo từ evidence đã xác thực.
Workflow profile mặc định được tự chọn: `standard` cho cả feature ứng dụng có
auth, permission, migration hoặc dữ liệu nhạy cảm; các dấu hiệu này tăng mức
kiểm tra nhưng không làm workflow cứng lại. Chỉ thao tác production hoặc
destructive mới tự nâng lên `critical`. `fast` dành cho thay đổi nhỏ ít rủi ro;
`advisory` chỉ phân tích, không sửa source.

Trong `standard`/`fast`, lỗi vận hành như timeout, phiên trùng, reporting drift
hoặc file source phát sinh hợp lệ được retry/chuẩn hóa có giới hạn. Hết retry,
workflow chuyển `PAUSED` để tiếp tục được, không khóa project ở `BLOCKED`.
Runtime vẫn chặn cứng `.biexce`, Git, secret/credential, đường dẫn ngoài project
và xung đột với task song song. `critical` giữ exact writable scope đã duyệt.

Nếu project cũ đang `BLOCKED` vì Plan liệt kê thiếu một file source/test thông
thường, `standard`/`fast` đọc cả task state lẫn job history rồi chuyển task sang
BX Test để kiểm chứng workspace hiện tại. Test PASS thì tiếp tục Review; Test
FAIL tạo evidence cho vòng BX Fix giới hạn rồi bắt buộc retest. Cơ chế này áp
dụng chung cho mọi task CODE/FIX, không bỏ qua test và không mở quyền cho file
bảo vệ hoặc đường dẫn ngoài project.

Khi CODE/FIX trả `FAILED` kèm failed check xác định, runtime chuyển task sang
vòng BX Fix có giới hạn thay vì gọi lại cùng BX Code. Ở `standard`/`fast`, BX Fix
có thể sửa tối thiểu expectation cũ đã bị acceptance mới thay thế, nhưng không
được xóa, skip hoặc làm yếu coverage để lấy PASS.

Kiểm tra hoặc dừng workflow của dự án:

```text
biexce status
biexce auto off
```

Trạng thái Autopilot được lưu trong `.biexce/` của dự án. Khi Autopilot tắt,
các agent vẫn hoạt động độc lập ở chế độ hỗ trợ hằng ngày. Do các child hiện
dùng chung một working tree, runtime chỉ cho một `CODE/FIX` writer hoạt động tại
một thời điểm; các phase read-only vẫn có thể chạy song song. Parallel source
writer chỉ được bật khi có workspace/worktree isolation.

Task đạt trần ba vòng fix sẽ dừng an toàn ở `BLOCKED`. Nếu người dùng duyệt
một bản sửa giới hạn, dùng `biexce autopilot resolve --project <path> --action
manual-fix --reason "<phạm vi đã duyệt>"`. CLI chỉ ghi yêu cầu; runtime kiểm tra,
ghi audit và cho task quay lại bước Fix, Test và Review ở lần Director tiếp tục.

## Kiểm tra

```text
biexce status
biexce self-test
```

Một bản cài đặt hoạt động bình thường sẽ hiển thị routing của đủ 7 agent,
runtime guard ở trạng thái sẵn sàng và `ok: true` từ self-test. Khi endpoint
nội bộ truy cập được, kiểm tra inference thực bằng:

```text
biexce self-test --live-inference
```

## Tài liệu

- [Điều khiển và Autopilot](docs/CONTROL-QUICKSTART.md)
- [Cài đặt trên Windows](docs/INSTALL-WINDOWS.md)
- [Cài đặt trên Ubuntu/Linux](docs/INSTALL-UBUNTU.md)
- [Cài đặt trên macOS](docs/INSTALL-MACOS.md)
- [Hướng dẫn sử dụng agent](docs/AGENT-GUIDE.md)
- [Danh mục agent và skill](docs/AGENT-SKILL-CATALOG.md)
