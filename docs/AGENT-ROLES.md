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
| BX Test | QA độc lập | Map criterion → check; chỉ ghi managed report, không sửa source/test |
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

Trong Autopilot, runtime sở hữu lifecycle kết quả. Child ưu tiên gọi
`biexce_submit_result`; runtime chuẩn hóa metadata báo cáo không nhạy cảm còn
thiếu và bỏ qua field phụ. Nếu thiếu tool call, runtime tự tạo kết quả từ
artifact, diff thực, managed-command evidence và dòng cuối `BIEXCE_STATUS`.
Filesystem là nguồn sự thật, nên khai báo file của model không thể làm hỏng một
job hợp lệ. Stale identity, thay đổi thật ngoài scope, PASS thiếu evidence hoặc
kết quả gửi trễ vẫn bị từ chối.

Artifact ownership được bảo vệ hai lớp: static permission của role và runtime
write-scope hook. BX Plan chỉ ghi `MASTER_PLAN.md` cùng `.biexce/tasks/**`;
Project Brief, Codebase Brief và toàn bộ `.biexce/state/**` là read-only đối
với Plan. Role artifact/read-only không được chạy managed shell command.

### Cấu trúc giao việc v0.4

Bốn phần bắt buộc của `task-spec` vẫn là nền, nhưng mỗi lần giao việc phải
truyền đủ envelope: objective, approved context/artifacts, constraints,
owner role, writable files, read-only inputs/tools, expected output,
validation/evidence required, và out-of-scope. WIP từ 1 đến 4 nhưng mỗi task
vẫn chỉ có một owner; owner không tự động tạo thêm quyền tool hoặc mở rộng writable
boundary. Với defect có failing test sẵn, test là read-only evidence mặc định;
owner sửa là BX Fix, không phải BX Code.

## 4. Quy trình chuyển cấp (thứ tự bắt buộc, không nhảy cóc)

1. Task FAIL → Fix (tối đa **3 vòng**/task; `CHANGES REQUIRED` của Review
   tính là một vòng).
2. INCONCLUSIVE (thiếu môi trường/VPN/infra) → runtime retry, không đốt vòng
   fix; profile thường pause có thể tiếp tục, `critical` mới block theo contract.
3. Spec-defect / thay đổi material scope / task quá to → quay về Plan (plan revision —
   không tính vòng fix).
4. Hết 3 vòng hoặc plan revision quá 2 lần → **Người** quyết: re-plan / waive
   (ghi vào state) / tự làm tay.
5. Mọi waiver đều phải do người phát, Director ghi nhận — agent không tự waive.

## 5. Quy định chung bất biến (mọi agent)

- **Evidence trước — kết luận sau**: không có bằng chứng thì nói "chưa kiểm
  chứng", cấm nói "đã pass" (`evidence-format`).
- **Biên dữ liệu**: Zone C không được vào model. Zone A mặc định chỉ dùng local;
  ngoại lệ duy nhất là `bx-review` cloud được đọc raw scoped diff và source tối
  thiểu liên quan ở `TASK_REVIEW`/`INTEGRATION_REVIEW` khi user đã apply binding.
  Review vẫn read-only, không được mở rộng audit hoặc đọc secret. Director/Plan
  cloud chỉ nhận artifact Zone B đã chưng cất (`company/security-policy`).
- **Git mặc định**: agent không có quyền ghi Git; chỉ `status/diff/log`
  read-only làm bằng chứng. Quyền ghi chỉ được mở bằng policy công ty đã duyệt.
- **Baseline thực thi**: scheduler DAG, WIP 1–4, depth=1. Phase read-only chỉ
  chạy song song khi dependency đã xong và model quota còn chỗ. Một working tree
  chỉ có một `CODE/FIX` writer; writer song song cần isolation riêng.
- **Autonomous end-to-end**: sau Project Brief, Director gọi `biexce_drive`;
  runtime tự chạy Explore → Plan → Plan Review đến Gate 1, rồi các batch Code →
  Test → Fix → Review đến Integration Test → Integration Fix/Retest → Review và
  Gate 2. Không yêu cầu human gọi agent, xóa lock hoặc sửa state.
- **Workflow profile**: `auto` dùng `standard`; auth/security/migration/payment/
  dữ liệu nhạy cảm tăng risk flags và yêu cầu test/review tương ứng nhưng không
  tự làm workflow cứng lại. Chỉ production/destructive tự nâng `critical`;
  `fast` dành cho việc nhỏ, `advisory` không sửa source. Đây là policy workflow,
  không phải model profile và không thay quyền user chọn model từng agent.
- **Recovery profile thường**: timeout, phiên trùng, reporting drift và file
  source phát sinh hợp lệ được retry/chuẩn hóa có giới hạn; hết retry chuyển
  `PAUSED`, không bắt human sửa state. State/Git/secret/path ngoài project và
  xung đột task song song vẫn bị deny; `critical` giữ exact write scope.
- **Migration blocker cũ**: ở `standard`/`fast`, scope drift của CODE/FIX được
  nhận diện từ cả task state và job history rồi bắt buộc kiểm chứng lại qua
  `BX Test`. FAIL mới mở một vòng `BX Fix` và phải retest; PASS tiếp tục Review.
  Không có exception theo project/task. Source mutation của Explore/Plan/Test/
  Review và mọi protected boundary vẫn bị chặn cứng.
- **Control plane fail-closed**: permission source của cả 7 agent luôn
  `task: deny`; chỉ runtime guard được phép cấp allowlist cho Director khi
  project đang `RUNNING`. Workflow state còn bắt buộc đúng agent theo phase,
  WIP, write ownership, model quota, Gate 1/2 và fix cap; chọn Director hoặc gửi prompt không phải quyền chạy.
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

- Tĩnh: manifest v2 hash 7 agent + 59 skill; kiểm frontmatter mode/permission
  đúng bảng này; `verify.ps1` chặn lệch chuẩn.
- Runtime offline: test hermetic chứng minh phase ordering, hai Human Gate,
  trần 2 vòng plan, 3 vòng Fix, `INCONCLUSIVE` retry và recovery theo profile,
  mọi file state được ghi atomic. Job board bền vững và per-job lease chặn hai
  plugin instance cùng nhận một job. Scheduler chứng minh task disjoint chạy
  song song, writer xung đột phải chờ và giới hạn local concurrency được tuân
  thủ. Source mặc định cho phép 4 inference local đồng thời, có thể cấu hình
  trong khoảng 1–8 bằng `BIEXCE_LOCAL_CONCURRENCY`.
  Autonomous driver chứng minh drain nhiều batch, pause an toàn và hoàn thành
  task độc lập trước khi báo blocker.
  Runtime supervisor tự abort child khi timeout, user cancel hoặc Autopilot
  OFF; managed command có log cap và dọn process tree trước khi nhả lease.
  Contract test còn chặn result JSON sai, PASS thiếu exit code, file ngoài
  writable scope và kết quả đến trễ.
  Live acceptance phải kiểm tra model thực tuân thủ envelope, verdict và
  state beacon trước khi phát hành.
- Mọi thay đổi vai trò phải sửa đồng thời: agent .md + bảng RACI này +
  manifest — lệch một trong ba là lỗi release.
