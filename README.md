# BIEXCE cho OpenCode

BIEXCE bổ sung rule và skill kỹ thuật cho workflow **Plan/Build** gốc của
OpenCode. Cấu hình được sinh vào một thư mục riêng, không ghi đè cấu hình người
dùng và không phụ thuộc custom scheduler.

## Workflow mặc định

| Mode | Vai trò | Quyền |
| --- | --- | --- |
| `plan` | Khảo sát, làm rõ yêu cầu và lập kế hoạch | Chỉ đọc source |
| `build` | Code, test, debug và hoàn thiện | Được sửa project |

Người dùng chọn model độc lập cho từng mode. Ví dụ thường dùng:

- `plan`: model cloud để phân tích và review sâu.
- `build`: model local để code, test và sửa lỗi.

Hai mode dùng chung catalog skill BIEXCE. Chúng có thể gọi subagent chỉ-đọc
`explore` hoặc `general` cho các phần khảo sát độc lập; quyền sửa source vẫn tập
trung ở `build` để tránh xung đột.

## Yêu cầu

- OpenCode có trong `PATH`, hoặc đã đặt `OPENCODE_BINARY`.
- Python 3 có trong `PATH`.
- PowerShell 5.1+ trên Windows, hoặc `bash` trên Linux/macOS.
- Các provider/model dự định dùng đã xuất hiện trong catalog OpenCode.

## Cài CLI BIEXCE

Clone repository hoặc giải nén release package, sau đó chạy bộ cài tương ứng.
Bộ cài giữ các tệp tương thích legacy; launcher do `biexce basic setup` sinh ra
luôn dùng cấu hình Plan/Build cô lập và không nạp workflow 7-agent cũ.

Windows:

```powershell
.\bin\windows\install.cmd
```

Ubuntu/Linux:

```bash
chmod u+rx bin/linux/*.sh
./bin/linux/install.sh
source ~/.profile
```

macOS:

```bash
chmod u+rx bin/macos/*.command
./bin/macos/install.command
source ~/.zprofile
```

## Tạo cấu hình Plan/Build

Xem model ID chính xác trước:

```text
opencode models
```

Tạo một cấu hình mới. Thay hai model mẫu bằng model đang có trên máy:

```bash
biexce basic setup \
  --output "$HOME/.config/biexce/plan-build" \
  --plan-model openai/gpt-5.6-sol \
  --build-model biexce-local/vllm/Qwen/Qwen3.8-27B-FP8 \
  --opencode-config-dir "$HOME/.config/opencode" \
  --json
```

PowerShell:

```powershell
biexce basic setup `
  --output "$HOME\.config\biexce\plan-build" `
  --plan-model openai/gpt-5.6-sol `
  --build-model biexce-local/vllm/Qwen/Qwen3.8-27B-FP8 `
  --opencode-config-dir "$HOME\.config\opencode" `
  --json
```

Kiểm tra cấu hình:

```text
biexce basic status --config-dir <thu-muc-plan-build> --json
biexce basic doctor --config-dir <thu-muc-plan-build> --json
```

Mỗi lần setup phải dùng một thư mục output mới. Cách này làm cho bản build có
thể kiểm tra, rollback hoặc xóa mà không ảnh hưởng cấu hình OpenCode hiện tại.

## Chạy project

Linux/macOS:

```bash
cd /path/to/project
$HOME/.config/biexce/plan-build/bin/biexce-opencode
```

Windows:

```powershell
cd C:\path\to\project
& "$HOME\.config\biexce\plan-build\bin\biexce-opencode.cmd"
```

Trong OpenCode:

1. Chọn `plan`, gửi mục tiêu và yêu cầu lập kế hoạch.
2. Duyệt hoặc điều chỉnh kế hoạch.
3. Chuyển sang `build`, yêu cầu triển khai và chạy đầy đủ kiểm tra.

OpenChamber có thể quản lý cùng OpenCode instance. Hãy cấu hình nó chạy launcher
trên hoặc truyền đúng `OPENCODE_CONFIG_DIR`; nếu không, OpenChamber có thể nạp
lại cấu hình agent cũ.

## Nguyên tắc chất lượng

- User là authority cao nhất về scope và quyết định sản phẩm.
- Không claim hoàn thành nếu formatter/linter/typecheck/test/build liên quan
  chưa pass.
- Không xóa hoặc làm yếu test để lấy kết quả xanh.
- Chỉ load skill liên quan để tránh làm phình context.
- Không sửa ngoài project hoặc thực hiện hành động phá hủy nếu chưa được phép.

## Chế độ 7 agent cũ

Source của runtime 7 agent/Slim vẫn được giữ tạm thời để tương thích và phục vụ
migration. Đây là chế độ nâng cao, không còn là workflow mặc định được khuyến
nghị. Lệnh của chế độ này nằm dưới `biexce slim` và `biexce autopilot`.

## Kiểm tra source

```powershell
python -m unittest discover -s tests/basic -p "test_*.py" -q
python -m unittest discover -s tests/slim -p "test_*.py" -q
powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1 -SkipCli
```

## Đánh giá workflow

`biexce eval` thu metrics đã rút gọn từ OpenCode session export, JUnit và assessment
của người chạy. Evidence mặc định nằm ngoài project; workflow không bị thêm lock,
job board hoặc state machine. Xem [hướng dẫn evaluation](docs/EVALUATION.md).

## Tài liệu

- [Hướng dẫn Plan/Build](docs/OPENCODE-PLAN-BUILD.md)
- [Đánh giá workflow](docs/EVALUATION.md)
- [Cài đặt Windows](docs/INSTALL-WINDOWS.md)
- [Cài đặt Ubuntu/Linux](docs/INSTALL-UBUNTU.md)
- [Cài đặt macOS](docs/INSTALL-MACOS.md)
- [Catalog skill](docs/AGENT-SKILL-CATALOG.md)
