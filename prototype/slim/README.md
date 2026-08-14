# Prototype OpenCode + Slim + BIEXCE

Thư mục này là prototype cô lập cho kiến trúc ba lớp:

```text
OpenCode -> Oh My OpenCode Slim -> BIEXCE roles/skills/quality
```

Prototype không cài Slim, không sửa user-global và không thay runtime cũ. Nó
sinh một `OPENCODE_CONFIG_DIR` mới để kiểm tra mapping, model, permission, prompt
và lazy skills trước khi chạy acceptance live.

Các MCP kế thừa từ base config được giữ cấu hình nhưng tạm đặt `enabled: false`
trong output cô lập, tránh kết nối dịch vụ không liên quan khi chạy acceptance.

## Thành phần

- `routing.example.json`: ví dụ user chọn model riêng cho bảy role.
- `build_config.py`: sinh config cô lập, từ chối ghi vào user-global.
- `ACCEPTANCE.md`: điều kiện PASS offline và live.

Source of truth của compatibility, prompt, `/bx-auto`, template và recovery
bridge nằm trong `src/global/slim/`. Generator production nằm trong
`src/biexce_control/slim_config/`; prototype không giữ bản asset hay generator
thứ hai.

Runtime chỉ có một parent `orchestrator` với alias `BX-Director` và sáu custom
specialist. `bx-director` vẫn là tên role ở CLI/routing, nhưng được map sang
`orchestrator`; không tạo hai Director cạnh tranh.

Prototype bật `backgroundJobs.orchestratorWake` theo đúng schema Slim 2.2.13 để
Director có thể được đánh thức khi còn công việc chưa hoàn tất. Schema được khóa
bằng SHA-256 trong `compatibility.json`. Hành vi này vẫn phải được chứng minh
bằng acceptance live; config tĩnh không được xem là bằng chứng runtime.

BX Review bị chặn edit và chỉ được chạy các lệnh Git đọc dữ liệu. BX Test được
phép tạo/cập nhật test vì vị trí test thay đổi theo từng framework; giới hạn
"không sửa product source" của BX Test được kiểm soát bằng task ownership,
prompt, diff review và evidence, không được mô tả sai thành path permission chung.

## Kiểm tra offline

Từ repository root:

```powershell
python -m unittest discover -s tests/slim -p "test_*.py" -v
```

Sinh config vào một thư mục tạm mới trên Windows:

```powershell
$target = Join-Path $env:TEMP (
    "biexce-slim-prototype-" + [guid]::NewGuid().ToString("N")
)

python prototype/slim/build_config.py `
    --routing prototype/slim/routing.example.json `
    --output $target
```

Khi test với provider/model đã cấu hình riêng trên máy, truyền config hiện tại
làm nguồn **chỉ đọc**. Generator chỉ lấy provider catalog rồi sinh output cô
lập; không sửa file nguồn:

```powershell
python prototype/slim/build_config.py `
    --routing path\to\routing.json `
    --base-opencode "$HOME\.config\opencode\opencode.json" `
    --output $target
```

Linux/macOS:

```bash
target="$(mktemp -d)/opencode-config"
python3 prototype/slim/build_config.py \
  --routing prototype/slim/routing.example.json \
  --base-opencode "$HOME/.config/opencode/opencode.json" \
  --output "$target"
```

Output gồm `opencode.json`, `oh-my-opencode-slim.json`, prompt, `/bx-auto`,
workflow template, đúng các skill được allowlist, recovery bridge, package pin
và `runtime.env.example`. Xóa thư mục tạm sau khi
kiểm tra xong. Nếu một custom provider có trong base config nhưng model được
chọn không có trong catalog của provider đó, generator dừng ngay thay vì tạo
một config live sai.

## Giới hạn Step 1

OpenCode hiện quan sát trên máy phát triển là 1.18.4, còn Slim 2.2.13 pin SDK và
plugin 1.18.13. Config sinh ra vì vậy có `opencode-ai@1.18.13` làm binary test
cục bộ; nó không nâng CLI global. Config offline có thể PASS nhưng chưa được xem
là live PASS. Việc chạy plugin, hiển thị child trong OpenChamber, song song và
restart phải dùng config cô lập và chỉ thực hiện sau khi user duyệt bước live;
không nâng hoặc cài đè user-global trong bước này.
