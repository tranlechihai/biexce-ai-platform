# BIEXCE — Bộ agent cho OpenCode

BIEXCE AGENTS cung cấp 7 agent hỗ trợ quy trình phát triển phần mềm trên OpenCode
Desktop và TUI. Bộ cài đặt theo tài khoản người dùng sẽ đăng ký agent, skill,
model routing, runtime guard và Autopilot theo từng dự án mà không cần quyền
Administrator hoặc `sudo`.

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

Thiết lập tương tác:

```text
biexce setup
```

Thiết lập không tương tác với một model mặc định và model riêng cho agent nếu
cần:

```text
biexce setup --model <provider/model> --agent bx-code=<provider/model> --yes
```

Provider nội bộ tùy chọn đọc endpoint từ biến môi trường
`BIEXCE_LOCAL_BASE_URL`. Giá trị phải là OpenAI-compatible base URL kết thúc
bằng `/v1`. Hãy khởi động lại OpenCode sau khi đổi endpoint hoặc model routing.

## Sử dụng Autopilot

Tại thư mục dự án cần chạy:

```text
biexce auto on
```

Mở cùng thư mục bằng OpenCode, chọn `Bx-Director`, rồi cung cấp mục tiêu, ràng
buộc và definition of done. BIEXCE sẽ dừng tại Human Gate 1 trước khi triển
khai và Human Gate 2 trước khi hoàn tất. Việc duyệt được thực hiện trực tiếp
trong OpenCode Desktop hoặc TUI.

Kiểm tra hoặc dừng workflow của dự án:

```text
biexce status
biexce auto off
```

Trạng thái Autopilot được lưu trong `.biexce/` của dự án. Khi Autopilot tắt,
các agent vẫn hoạt động độc lập ở chế độ hỗ trợ hằng ngày.

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
