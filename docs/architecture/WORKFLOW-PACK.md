# BIEXCE workflow pack trên Slim

[← Kiến trúc đích](TARGET-ARCHITECTURE.md)

## Source of truth

Workflow mới nằm tại `src/global/slim/`:

```text
slim/
├── commands/bx-auto.md
├── prompts/                    # BX Director + 6 specialist
├── templates/                  # Brief, Plan, Task, Checkpoint, Report
├── plugins/biexce-recovery.js
├── runtime/recovery-core.js
└── compatibility.json
```

`prototype/slim/` chỉ còn CLI và routing mẫu để sinh config cô lập. Generator
production nằm trong `src/biexce_control/slim_config/`; không có bản prompt,
plugin hoặc runtime thứ hai trong prototype.

## Cách chạy workflow

Trong OpenCode/OpenChamber đã nạp config Slim, user chạy:

```text
/bx-auto <mục tiêu cụ thể>
```

Command được cố định chạy bằng `orchestrator`, alias hiển thị là `BX-Director`.
Director dùng native TODO/session của OpenCode và background agents của Slim. Nó
không tạo scheduler, WIP counter, lock, lease hoặc workflow-state JSON riêng.

## Luồng chất lượng

```text
User -> Director -> Explore -> Plan -> Plan Review -> Gate 1
     -> Code -> Test -> Fix nếu cần -> Retest -> Task Review
     -> Integration Test -> Integration Review -> Gate 2 -> Final Report
```

- Task độc lập, không trùng ownership có thể chạy song song.
- Writer có ownership trùng nhau chạy tuần tự hoặc dùng worktree có chủ đích.
- Scope là intent/subsystem; danh sách file trong task là dự kiến, không phải
  khóa tuyệt đối.
- Test cũ trái với requirement mới đã duyệt được chuyển thành test-update task,
  không trở thành runtime blocker.
- Retry lặp cùng lỗi phải dừng để Director phân tích lại task/plan; không tạo
  vòng lặp vô hạn và không bắt user sửa state nội bộ.

## Quyền user và gate

User có quyền cao nhất đối với start, pause, cancel, reprioritize, retry, revise,
waive và accept. Gate 1/Gate 2 là câu hỏi trong parent session, không phải lệnh
CLI hoặc lock file. Waiver phải được ghi vào artifact và giữ nguyên evidence
FAIL/INCONCLUSIVE; waiver không biến evidence thành PASS.

Chỉ hard-stop khi có ranh giới an toàn thật: thiếu quyền truy cập, secret,
destructive/production mutation, writer conflict chưa cô lập, hoặc quyết định
sản phẩm mâu thuẫn cần user chốt.

## Artifact bền vững

Template được sinh vào `biexce/templates/`. Khi chạy trong project, workflow chỉ
giữ tài liệu có giá trị bàn giao dưới `.biexce/`:

- `PROJECT_BRIEF.md`, `CODEBASE_BRIEF.md`, `MASTER_PLAN.md`;
- `tasks/*.md`;
- `CHECKPOINT.md`;
- `reports/FINAL_REPORT.md` và evidence cần thiết.

`CHECKPOINT.md` chỉ là handoff dễ đọc. OpenCode/Slim session vẫn là runtime
authority.

## Recovery sau restart

`biexce-recovery.js` chỉ đọc native session, status, TODO, message và child của
OpenCode. Khi thấy parent idle còn TODO chưa xong, bridge gửi một recovery
reminder vào chính parent để Director kiểm tra artifact và tiếp tục session con
cũ hoặc re-dispatch đúng một lần. Bridge không tạo scheduler, lock, lease hoặc
workflow-state riêng.

Lỗi API hoặc plugin được ghi vào OpenCode application log; không bị nuốt im
lặng. Retry khởi động được giới hạn và không thay thế cơ chế background của
Slim. Nếu provider chưa sẵn sàng, session vẫn giữ nguyên để tiếp tục sau đó.

## CLI cô lập

Không cài global trong bước này. Sinh config từ model routing đã apply:

```powershell
biexce slim setup --output <fresh-directory>
biexce slim status --config-dir <directory>
biexce slim doctor --config-dir <directory>
```

`status` PASS khi cấu trúc, role, model, command, template, recovery bridge và pin
đúng. `doctor` chỉ PASS khi dependency cục bộ cũng đã được cài trong chính output.
Generator từ chối ghi vào user-global và từ chối overwrite output có sẵn.

Khi chạy, dùng launcher được sinh trong output:

```bash
export OPENCODE_BINARY="<directory>/bin/biexce-opencode"
```

Launcher cô lập config/plugin legacy bằng một `XDG_CONFIG_HOME` riêng nhưng không
đổi data directory chứa auth. Vì vậy provider/model user đã chọn vẫn hoạt động,
trong khi custom runtime cũ không thể can thiệp vào workflow Slim.

## Ranh giới migration

Workflow pack mới chưa tự thay cấu hình global và chưa xóa runtime legacy. Chỉ
sau acceptance workflow, recovery, parallel, user-decision và full-stack trên
Windows/Ubuntu mới chuyển installer mặc định và loại runtime cũ.
