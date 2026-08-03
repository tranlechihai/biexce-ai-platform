# Cài đặt trên macOS

BIEXCE hỗ trợ cả máy Mac Apple Silicon và Intel.

## Yêu cầu

- `python3`, Git nếu cài bằng cách clone và OpenCode.
- Không cần quyền `sudo`.

## Cài đặt

```bash
git clone <repository-url>
cd <repository-directory>
chmod u+rx bin/macos/*.command
./bin/macos/install.command
```

Installer ghi các file do BIEXCE quản lý vào `~/.config/opencode` và đăng ký
lệnh global trong `~/.zprofile` đối với zsh hoặc `~/.profile` đối với bash.

Sau khi thấy `INSTALL PASS`, mở cửa sổ Terminal mới:

```bash
command -v biexce
biexce setup
biexce status
biexce self-test
```

Nếu Gatekeeper chặn command đã tải xuống, Control-click vào file, chọn
**Open** và xác nhận đây là nguồn tin cậy.

## Endpoint model nội bộ

Chỉ máy sử dụng provider nội bộ tùy chọn mới cần biến này:

```bash
export BIEXCE_LOCAL_BASE_URL='http://<internal-host>:<port>/v1'
```

Lưu biến trong cấu hình shell đã được công ty phê duyệt. Không commit endpoint
thật hoặc credential. Khởi động lại OpenCode sau khi đổi giá trị.

## Sử dụng Autopilot

```bash
cd /path/to/project
biexce auto on
opencode
```

Chọn `Bx-Director` trong Desktop hoặc TUI. Human Gate 1 và 2 được xử lý trực
tiếp trong OpenCode. Dừng workflow bằng `biexce auto off`.

## Kiểm tra và chẩn đoán

```bash
./bin/macos/verify.command
./bin/macos/doctor.command
biexce self-test --live-inference
```

Chỉ chạy kiểm tra live inference khi provider đã chọn truy cập được. Nếu shell
không tìm thấy `biexce`, mở terminal mới hoặc source profile file tương ứng.
