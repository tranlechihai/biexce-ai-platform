# Workflow OpenCode Plan/Build

## Mục tiêu

Workflow mặc định của BIEXCE chỉ có hai mode gốc của OpenCode:

- `plan`: phân tích read-only, lập kế hoạch và nêu rủi ro.
- `build`: triển khai, kiểm tra, sửa lỗi và bàn giao evidence.

BIEXCE không duy trì job board, lock, WIP slot hay state machine riêng trong chế
độ này. OpenCode quản lý session, permission và provider; user quyết định scope
và thời điểm chuyển từ Plan sang Build.

## Cấu trúc bản cấu hình sinh ra

```text
plan-build/
├── AGENTS.md
├── biexce-basic.json
├── opencode.json
├── bin/
│   ├── biexce-opencode
│   └── biexce-opencode.cmd
├── prompts/
│   ├── plan.md
│   └── build.md
└── skills/
    └── <skill>/SKILL.md
```

Generator chỉ kế thừa catalog `provider`, `mcp` và `watcher` từ cấu hình nguồn.
Nó loại bỏ plugin, custom agent và scheduler cũ, sau đó tạo đúng hai binding
model do user chọn.

## Setup

```text
biexce basic setup \
  --output <thu-muc-moi> \
  --plan-model <provider/model> \
  --build-model <provider/model> \
  --opencode-config-dir <thu-muc-opencode> \
  --json
```

Output phải là thư mục chưa tồn tại. Generator từ chối ghi trực tiếp vào thư
mục cấu hình OpenCode global để giữ rollback đơn giản.

## Kiểm tra

`basic status` kiểm tra cấu trúc tĩnh:

```text
biexce basic status --config-dir <thu-muc-moi> --json
```

`basic doctor` kiểm tra thêm OpenCode CLI:

```text
biexce basic doctor --config-dir <thu-muc-moi> --json
```

Kết quả sẵn sàng phải có `ok: true` và `ready_to_run: true`.

## Đổi model

Không sửa model ID trong source BIEXCE. Khi provider thay model, hãy tạo một
output mới bằng model ID lấy từ `opencode models`. Sau khi doctor pass, đổi
launcher của OpenChamber/OpenCode sang output mới; output cũ là bản rollback.

## Skill và context

Toàn bộ skill được đóng gói, nhưng prompt yêu cầu chỉ load skill liên quan tới
task hiện tại. Cách này giữ khả năng chuyên môn mà không đưa toàn bộ catalog vào
mỗi request.

## Chạy qua OpenChamber

OpenChamber phải khởi động OpenCode bằng launcher trong `bin/`, hoặc có cùng các
biến môi trường mà launcher đặt. Nếu OpenChamber đang chạy bằng một config cũ,
hãy dừng instance đó rồi tạo instance mới trỏ tới launcher Plan/Build.

## Chế độ legacy

Runtime 7 agent/Slim được giữ trong source để migration và regression. Không sử
dụng đồng thời Plan/Build và legacy runtime cho cùng một session.
