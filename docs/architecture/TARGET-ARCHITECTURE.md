# Kiến trúc đích và workflow

[← Tổng quan kiến trúc](OPENCODE-SLIM-BIEXCE.md)

## Trách nhiệm từng lớp

### Lớp 1 — OpenCode

OpenCode là nguồn trạng thái runtime duy nhất cho:

- parent/child session;
- background task/session ID;
- `busy`, `idle`, retry và terminal result;
- permission UI và tool permission;
- provider/model thực tế;
- session lifecycle và cancellation.

Không dùng file JSON của BIEXCE để kết luận child còn chạy, đã chết hay hoàn
thành.

### Lớp 2 — Oh My OpenCode Slim

Slim là plugin/orchestration engine thực tế, không chỉ là tài liệu tham khảo.

Slim chịu trách nhiệm:

- biến parent orchestrator thành scheduler thay vì worker chính;
- dispatch background specialists;
- theo dõi child bằng OpenCode live session;
- reconcile terminal result;
- scheduling theo dependency;
- chạy song song task độc lập;
- tránh writer conflict bằng ownership;
- tuần tự hóa hoặc dùng worktree khi task có nguy cơ trùng file;
- nhận biết child stopped/unreconciled sau restart và hỗ trợ re-dispatch;
- hiển thị hoạt động child qua OpenCode/OpenChamber hoặc multiplexer/companion.

Job board của Slim chỉ là projection quan sát. Nó không được dùng làm khóa hoặc
nguồn sự thật để block toàn project.

### Lớp 3 — BIEXCE

BIEXCE cung cấp:

- bảy agent và trách nhiệm từng role;
- prompt và routing instruction;
- per-agent model routing;
- skill catalog và lazy skill loading;
- company/project knowledge;
- Project Brief, Master Plan và task contracts;
- Gate 1/Gate 2;
- test strategy, review policy và Definition of Done;
- checkpoint và báo cáo cuối;
- CLI `setup`, `doctor`, `status`, model/profile management.

BIEXCE không còn sở hữu scheduler, lease, child liveness, retry state machine
hoặc job lock riêng.

## Mapping bảy agent

Slim có parent orchestrator riêng. Mapping ưu tiên là:

| BIEXCE role | Slim/OpenCode identity | Trách nhiệm |
|---|---|---|
| BX Director | `orchestrator`, alias `BX-Director` | Phỏng vấn, điều phối, tổng hợp, gate |
| BX Explore | custom `bx-explore`, mode `all` | Khảo sát codebase, read-only |
| BX Plan | custom `bx-plan`, mode `all` | Master Plan và task contracts |
| BX Code | custom `bx-code`, mode `all` | Implement task |
| BX Test | custom `bx-test`, mode `all` | Test strategy, test/evidence |
| BX Fix | custom `bx-fix`, mode `all` | Sửa defect có evidence |
| BX Review | custom `bx-review`, mode `all` | Plan/task/integration review |

Slim 2.2.13 yêu cầu `displayName` là identifier an toàn, không chứa khoảng
trắng; vì vậy alias runtime là `BX-Director`, còn nhãn tài liệu vẫn là “BX
Director”. Không fork/sửa core Slim chỉ để đổi internal ID. CLI giữ mapping
`bx-director <-> orchestrator`.

Mode `all` cho phép sáu specialist vừa được chọn/gọi trực tiếp bởi user, vừa
được Orchestrator dispatch làm child. Một bridge cấu hình mỏng chạy sau Slim chỉ
điều chỉnh mode của registry hiện hữu; không đăng ký bản sao agent và không tạo
authority thứ hai. Runtime acceptance phải xác nhận không có entry legacy
`bx-director` cạnh `orchestrator`.

Các built-in agent Slim không dùng phải được disable hoặc không đưa vào routing
prompt để tránh hai hệ agent cạnh tranh nhau.

## Workflow nghiệp vụ

```text
User request
  -> BX Director interview nếu cần
  -> BX Explore
  -> BX Plan
  -> BX Review: Plan Review
  -> Human Gate 1
  -> DAG execution
       -> BX Code
       -> BX Test
          -> source/test FAIL -> BX Fix -> BX Test
          -> PASS -> BX Review: Task Review
  -> BX Test: Integration Test
  -> BX Review: Integration Review
  -> Human Gate 2
  -> Final Report
```

Gate 1/Gate 2 dùng question/wait trong giao diện OpenCode/OpenChamber. Gate là
quyết định workflow của BIEXCE, không phải lock JSON hoặc CLI action.

User có thể can thiệp ở bất kỳ thời điểm nào. Director phải ưu tiên message mới
của user, cập nhật plan/task/checkpoint rồi điều phối tiếp.

## State và artifact

Chỉ giữ artifact có giá trị lâu dài:

```text
.biexce/
├── PROJECT_BRIEF.md
├── CODEBASE_BRIEF.md          # chỉ khi cần
├── MASTER_PLAN.md
├── tasks/
├── CHECKPOINT.md
└── reports/
```

- `CHECKPOINT.md` là context để resume, không phải lock.
- Task ID/child status lấy từ OpenCode/Slim trong runtime hiện hành.
- Không dùng `AUTOPILOT_WORKFLOW.json`, `PROJECT_STATE.json`, scheduler state,
  lease hoặc manual-recovery JSON làm authority.
- Artifact thiếu là việc cần tạo/bổ sung, không mặc định là terminal blocker.

## Quyền sửa source và scope

Trong profile thông thường:

- BX Code/Fix được sửa file hợp lệ trong project để hoàn thành task.
- Task contract mô tả intent và ownership, không phải danh sách file tuyệt đối.
- File phát sinh hợp lý ngoài dự đoán được ghi vào result và đưa qua Review,
  không tự động block.
- BX Test được tạo/cập nhật test cần thiết cho acceptance hiện hành.
- Test cũ lỗi thời được cập nhật khi requirement mới đã được user/Gate 1 duyệt;
  BX Review phải kiểm tra việc sửa test không che defect.
- Generated files/cache được ignore hoặc cleanup, không tính là source breach.

Vị trí test khác nhau giữa framework nên prototype không giả lập một path
permission chung cho BX Test. Quyền test-only được thực thi bằng ownership trong
task, prompt, evidence và diff review; BX Review mới là role bị khóa read-only
trực tiếp ở tool level (`edit: deny`, bash mutation bị deny).

Chỉ hard-stop khi:

- truy cập ngoài project chưa có permission;
- secret/credential leak;
- mutation `.git` không được phép;
- production/destructive operation chưa được duyệt;
- writer conflict chưa được cô lập;
- yêu cầu mâu thuẫn cần user quyết định.

## Chạy song song và writer conflict

Parallelism dựa trên dependency và ownership thực tế:

- read-only Explore/Review có thể chạy song song khi không phụ thuộc kết quả;
- writer khác file/subsystem rõ ràng có thể chạy song song;
- writer trùng hoặc chưa rõ file phải chạy tuần tự;
- task lớn/rủi ro có thể dùng Git worktree riêng;
- review không chạy trước khi writer cần review đã terminal.

Worktree là cơ chế tùy chọn có chủ đích, không giả định Slim tự động cô lập mọi
writer. Merge/integration cuối phải được kiểm tra trên final workspace.

## Liên kết tiếp theo

- [Quyền user, quality và vận hành](POLICY-OPERATIONS.md)
- [Kế hoạch migration](MIGRATION.md)
- [Acceptance bắt buộc](ACCEPTANCE.md)
