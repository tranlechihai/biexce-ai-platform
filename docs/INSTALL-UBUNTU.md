# Cài đặt trên Ubuntu/Linux

## Yêu cầu

- `bash`, `python3`, Git nếu cài bằng cách clone và OpenCode.
- Không cần quyền `sudo`.

## Cài đặt

```bash
git clone <repository-url>
cd <repository-directory>
chmod u+rx bin/linux/*.sh
./bin/linux/install.sh
```

Installer ghi các file do BIEXCE quản lý vào `~/.config/opencode` và đăng ký
`~/.config/opencode/biexce-bin` trong `~/.profile`.

Sau khi thấy `INSTALL PASS`, mở phiên SSH hoặc terminal mới:

```bash
command -v biexce
biexce setup
biexce status
biexce self-test
```

Thiết lập model không tương tác:

```bash
biexce setup --model provider/model --yes
biexce model validate
```

`biexce model list` phân biệt model thấy trong catalog với trạng thái credential
và inference. Nếu provider báo `NOT AUTHENTICATED`, mở OpenCode, chạy `/connect`,
sau đó kiểm tra lại bằng `biexce status`. Cảnh báo không ngăn user lưu model đã
chọn.

## Endpoint model nội bộ

Chỉ máy sử dụng provider nội bộ tùy chọn mới cần biến này:

```bash
export BIEXCE_LOCAL_BASE_URL='http://<internal-host>:<port>/v1'
read -rsp 'Bifrost Virtual Key: ' BIEXCE_LOCAL_VIRTUAL_KEY && echo
export BIEXCE_LOCAL_VIRTUAL_KEY
```

Chỉ cần biến key khi gateway bắt buộc Bifrost Virtual Key. Lưu endpoint và key
bằng secret store hoặc môi trường đã được công ty phê duyệt; không ghi key vào
repository hay shell history. Khởi động lại OpenCode/OpenChamber sau khi đổi
giá trị.

## Sử dụng Autopilot

```bash
cd /path/to/project
biexce auto on
opencode
```

Chọn `Bx-Director` trong TUI. Human Gate 1 và 2 được xử lý trực tiếp trong
OpenCode. Dừng workflow bằng `biexce auto off`.

## Kiểm tra và chẩn đoán

```bash
./bin/linux/verify.sh
./bin/linux/doctor.sh
biexce self-test --live-inference
```

Chỉ chạy kiểm tra live inference khi provider đã chọn truy cập được. Nếu shell
không tìm thấy `biexce`, mở phiên mới hoặc chạy `source ~/.profile`.
