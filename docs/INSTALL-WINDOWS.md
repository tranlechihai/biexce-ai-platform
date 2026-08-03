# Cài đặt trên Windows

## Yêu cầu

- Windows PowerShell 5.1 trở lên.
- Python 3 và OpenCode có trong `PATH`.
- Không cần quyền Administrator.

## Cài đặt

Clone repository hoặc giải nén đầy đủ release package. Tại thư mục BIEXCE,
chạy:

```powershell
.\bin\windows\install.cmd
```

Installer ghi các file do BIEXCE quản lý vào
`%USERPROFILE%\.config\opencode`, đăng ký lệnh global `biexce` vào `PATH` của
người dùng, kiểm tra bản cài đặt và tự rollback nếu verification thất bại.

Sau khi thấy `INSTALL PASS`, đóng terminal cũ và mở cửa sổ PowerShell mới:

```powershell
Get-Command biexce
biexce setup
biexce status
biexce self-test
```

Nếu provider chưa được kết nối, dùng `/connect` và `/models` trong OpenCode
trước khi setup. Khởi động lại OpenCode sau khi thay đổi model routing.

## Endpoint model nội bộ

Chỉ máy sử dụng provider nội bộ tùy chọn mới cần thiết lập này. Lưu
OpenAI-compatible base URL bằng biến môi trường của người dùng:

```powershell
[Environment]::SetEnvironmentVariable(
    'BIEXCE_LOCAL_BASE_URL',
    'http://<internal-host>:<port>/v1',
    'User'
)
```

Mở terminal mới và khởi động lại OpenCode sau khi đổi giá trị. Không commit
endpoint công ty, credential hoặc Authorization header vào source repository.

## Sử dụng Autopilot

```powershell
cd D:\path\to\project
biexce auto on
opencode
```

Chọn `Bx-Director` trong OpenCode và cung cấp mục tiêu dự án. Human Gate 1 và 2
được duyệt hoặc từ chối trực tiếp trong OpenCode. Dừng Autopilot bằng:

```powershell
biexce auto off
```

## Kiểm tra và chẩn đoán

Khi vẫn còn source đã clone hoặc release package đã giải nén:

```powershell
.\bin\windows\verify.cmd
.\bin\windows\doctor.cmd
```

Khi endpoint nội bộ truy cập được:

```powershell
biexce self-test --live-inference
```

Nếu terminal mới không tìm thấy `biexce`, hãy đăng xuất rồi đăng nhập lại hoặc
kiểm tra `PATH` của người dùng có chứa:

```text
%USERPROFILE%\.config\opencode\biexce-bin
```

Installer giữ nguyên cấu hình OpenCode nằm ngoài allowlist do BIEXCE quản lý.
Cần giải quyết xung đột nếu `opencode.json` và `opencode.jsonc` cùng tồn tại
trước khi cài đặt.
