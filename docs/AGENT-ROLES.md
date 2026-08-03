# Quy định vai trò đội agent BIEXCE

Tài liệu quản trị cho người (lead/dev) — bản máy-đọc nằm trong từng
`src/global/agents/bx-*.md`. Mọi agent theo cùng khung hợp đồng vai trò:
Trách nhiệm · Không-phải-việc-của-mình · Input bắt buộc · Quy trình · Output
chuẩn · Thước chất lượng · Luật escalate · Điều cấm.

## 1. Đội hình và một câu định nghĩa

| Agent | Vai người thật tương đương | Một câu |
|---|---|---|
| BX Director | Giám đốc dự án + điều phối | Chịu trách nhiệm end-to-end; giao việc đủ 4 phần; không bao giờ tự code |
| BX Plan | PM + Kiến trúc sư + Planner | Biến Brief thành MASTER_PLAN + story files; không bao giờ implement |
| BX Code | Developer | Diff nhỏ nhất đúng story file, kèm test; không vượt writable boundary |
| BX Fix | Debugger | Sửa đúng root cause theo evidence; không refactor, không "tiện tay" |
| BX Test | QA độc lập | Map mọi criterion → check; PASS/FAIL/INCONCLUSIVE trung thực |
| BX Review | Tech lead độc lập | Red-team plan + review diff; verdict không nể nang |
| BX Explore | Scout/Librarian | Định vị code + chưng cất Codebase Brief; cầu nối biên dữ liệu |

## 2. Ma trận trách nhiệm (R = làm, A = chịu trách nhiệm, C = tham vấn, I = được báo)

| Việc | Director | Plan | Code | Fix | Test | Review | Explore | Người |
|---|---|---|---|---|---|---|---|---|
| Chốt phạm vi (Brief) | A/R | C | — | — | — | — | — | C→duyệt |
| Codebase Brief | A | I | — | — | — | — | R | — |
| Kiến trúc + task DAG | A | R | — | — | — | C (red-team) | C | duyệt GATE 1 |
| Viết code + test của task | A | — | R | — | — | — | — | — |
| Chạy check, evidence | A | — | — | — | R | I | — | — |
| Sửa lỗi (fail/finding) | A | C (nếu spec-defect) | — | R | I | I | — | — |
| Verdict diff | A | — | — | — | C (evidence) | R | — | — |
| Regression B4 | A | C (chiến lược) | — | — | R | R (tổng) | — | — |
| Nghiệm thu cuối | R (báo cáo) | — | — | — | — | — | — | A (GATE 2) |
| Runtime state/beacon | R/A | — | — | — | — | — | — | I |

Không ô nào có 2 chữ R cho cùng sản phẩm → không chồng chức năng; mỗi hàng có
đúng 1 A → không hở trách nhiệm.

## 3. Hợp đồng tương tác (ai gọi ai, truyền gì, nhận gì)

```text
Người ⇄ Director (duy nhất ở Autopilot)
Director → Explore  [câu hỏi/y.c Brief]             → Brief / trả lời path:line
Director → Plan     [Brief + Codebase Brief]        → MASTER_PLAN + tasks/
Director → Review   [plan]                           → PLAN OK / NEEDS REVISION
Người   → Gate 1    [plan + red-team]                → approve rõ ràng
Director → Code     [story file đủ 4 phần]          → diff report + evidence tự kiểm
Director → Test     [diff + acceptance criteria]    → bảng criteria→check + verdict
Director → Fix      [evidence FAIL / findings]      → root cause + diff + evidence
Director → Review   [diff+story+test]                → findings + verdict
Director → Test     [toàn bộ task]                   → integration/regression verdict
Director → Review   [integration]                    → overall verdict
Người   → Gate 2    [integration + final report]     → nghiệm thu rõ ràng
(Daily assist: Người -> agent bất kỳ; agent được chọn chỉ route, không tự gọi agent khác)
```

Quy tắc truyền: **mọi lệnh giao việc đủ envelope** (objective / output format /
owner + writable files + read-only inputs/tools / out-of-scope — skill
`task-spec`); kết quả trả về phải khớp format vai trò; thiếu input bắt buộc →
agent hỏi lại một lần, không đoán.

### Cấu trúc giao việc v0.4

Bốn phần bắt buộc của `task-spec` vẫn là nền, nhưng mỗi lần giao việc phải
truyền đủ envelope: objective, approved context/artifacts, constraints,
owner role, writable files, read-only inputs/tools, expected output,
validation/evidence required, và out-of-scope. WIP=1 nghĩa là mỗi task chỉ có
một owner; owner không tự động tạo thêm quyền tool hoặc mở rộng writable
boundary. Với defect có failing test sẵn, test là read-only evidence mặc định;
owner sửa là BX Fix, không phải BX Code.

## 4. Quy trình chuyển cấp (thứ tự bắt buộc, không nhảy cóc)

1. Task FAIL → Fix (tối đa **3 vòng**/task; `CHANGES REQUIRED` của Review
   tính là một vòng).
2. INCONCLUSIVE (thiếu môi trường/VPN/infra) → không đốt vòng fix; Director
   xử lý blocker hoặc đánh dấu `blocked`.
3. Spec-defect / vượt writable boundary / task quá to → quay về Plan (plan revision —
   không tính vòng fix).
4. Hết 3 vòng hoặc plan revision quá 2 lần → **Người** quyết: re-plan / waive
   (ghi vào state) / tự làm tay.
5. Mọi waiver đều phải do người phát, Director ghi nhận — agent không tự waive.

## 5. Quy định chung bất biến (mọi agent)

- **Evidence trước — kết luận sau**: không có bằng chứng thì nói "chưa kiểm
  chứng", cấm nói "đã pass" (`evidence-format`).
- **Biên dữ liệu**: nội dung source/diff/secret không được vào ngữ cảnh model
  cloud; đường lên cloud duy nhất là artifact đã chưng cất (Brief/plan/spec)
  (`company/security-policy`).
- **Git mặc định**: agent không có quyền ghi Git; chỉ `status/diff/log`
  read-only làm bằng chứng. Quyền ghi chỉ được mở bằng policy công ty đã duyệt.
- **Baseline thực thi**: tuần tự WIP=1, depth=1, không parallel. Chỉ thay đổi
  khi platform capacity và runtime configuration đã được phê duyệt rõ ràng.
- **Control plane fail-closed**: permission source của cả 7 agent luôn
  `task: deny`; chỉ runtime guard được phép cấp allowlist cho Director khi
  project đang `RUNNING`. Workflow state còn bắt buộc đúng agent theo phase,
  WIP=1, Gate 1/2 và fix cap; chọn Director hoặc gửi prompt không phải quyền chạy.
- **Không đổi vai**: agent được chọn là vai có thẩm quyền; bị yêu cầu làm việc
  của vai khác thì chỉ ra đúng agent, không tự làm thay.
- **Model/effort do user và cấu hình chọn** — agent không tự đổi model.
- Secrets/production/paths ngoài repo: cấm tuyệt đối (permission đã enforce).

## 6. Thứ tự ưu tiên, định tuyến và mức độ hoàn thiện của skill

Thứ tự bắt buộc: (1) permission deny + company/security policy, (2)
`AGENTS.md` gần nhất, (3) artifact `.biexce/` đã được phê duyệt, (4) request
hoặc delegation hiện tại. Lớp thấp chỉ được thu hẹp, không được nới lỏng lớp
cao; conflict phải dừng hành động liên quan và escalate.

Agent sai vai phải trả `ROUTE: <agent> - <reason>`, không làm thay một phần.
Skill có `[SKELETON]`, placeholder ID, hoặc `TODO` chưa giải quyết được xem là
chưa sẵn sàng và không được dùng làm authority. Company/security policy không
được project config override.

## 7. Kiểm chứng tuân thủ

- Tĩnh: manifest v2 hash 7 agent + 50 skill; kiểm frontmatter mode/permission
  đúng bảng này; `verify.ps1` chặn lệch chuẩn.
- Runtime offline: test hermetic chứng minh phase ordering, hai Human Gate,
  trần 2 vòng plan, 3 vòng Fix, `INCONCLUSIVE`/vượt trần chuyển `BLOCKED` và
  mọi file state được ghi atomic. Lock project-local còn chặn hai plugin
  instance cùng delegate, nên WIP=1 không chỉ dựa vào biến nhớ của một process.
  Live acceptance phải kiểm tra model thực tuân thủ envelope, verdict và
  state beacon trước khi phát hành.
- Mọi thay đổi vai trò phải sửa đồng thời: agent .md + bảng RACI này +
  manifest — lệch một trong ba là lỗi release.
