# Quyền user, quality và vận hành

[← Tổng quan kiến trúc](OPENCODE-SLIM-BIEXCE.md)

## Quyền tối cao của user

User là người có quyền quyết định cao nhất đối với project đang làm. Director,
Plan, Review, Test và runtime chỉ tư vấn, cung cấp evidence và thực thi.

User có quyền:

- xác định hoặc thay đổi requirement, scope và Definition of Done;
- chọn kiến trúc, ưu tiên, mức chất lượng và trade-off;
- chọn model riêng cho từng agent;
- duyệt, từ chối hoặc yêu cầu sửa Plan/Gate;
- cho phép cập nhật test cũ khi acceptance mới làm test đó lỗi thời;
- yêu cầu replan, retry, đổi agent/model, tạm dừng, tiếp tục hoặc hủy workflow;
- chấp nhận rủi ro hoặc waive một tiêu chí với lý do được ghi audit;
- mở rộng write scope trong project;
- cho phép deployment/destructive operation qua xác nhận rõ ràng và permission
  UI phù hợp.

Khi user đã quyết định, BIEXCE phải chuyển quyết định thành task/workflow tiếp
theo và tiếp tục tự động. Không được yêu cầu user:

- sửa `.biexce/state/**`;
- chạy lệnh recovery nội bộ;
- clear lease/lock;
- gọi lại agent cụ thể;
- tự chỉnh job board hoặc scheduler JSON.

### Giới hạn không được làm sai lệch

Quyền user không được biến thành kết quả giả. Hệ thống luôn phải:

- báo đúng test/build/lint thực tế PASS hay FAIL;
- không che giấu evidence hoặc tự nhận hoàn thành khi chưa chạy check;
- không đưa secret/credential vào source, log hoặc report;
- không ghi ra ngoài project khi chưa có permission rõ ràng;
- không tự sửa `.git` hoặc thực hiện destructive/production action âm thầm;
- không để hai writer sửa cùng file mà không cô lập hoặc tuần tự hóa.

Nếu user chấp nhận một check đang FAIL hoặc waive tiêu chí, báo cáo phải ghi rõ
`WAIVED BY USER`, lý do, evidence còn fail và residual risk. Không đổi FAIL
thành PASS.

OpenCode permission UI là ranh giới thực thi cuối cùng cho thao tác cần xác
nhận. BIEXCE không được tạo thêm một lớp quyền thứ hai để bác bỏ quyết định hợp
lệ của user.

## Skill, knowledge và context

Không load toàn bộ catalog vào mọi prompt. Mỗi child chỉ nhận:

```text
Role prompt
+ task contract
+ 2–5 skill liên quan
+ project/company knowledge cần thiết
+ file/path hoặc search scope
+ expected evidence
```

Skill được gán theo agent thông qua cấu hình Slim. Company knowledge không thay
thế evidence từ source hiện tại.

## Model routing

User tự chọn model theo từng agent. BIEXCE không hard-code cloud/local.

CLI `biexce setup/model/profile` phải tạo hoặc cập nhật cấu hình Slim tương ứng,
không duy trì một routing authority cạnh tranh với Slim/OpenCode.

Ví dụ hợp lệ:

```text
BX Director  -> cloud mạnh
BX Plan      -> cloud mạnh
BX Review    -> cloud mạnh
BX Explore   -> local
BX Code      -> local
BX Test      -> local
BX Fix       -> local
```

Hoặc user có thể gắn local/cloud cho toàn bộ agent tùy project.

## Quality policy

Chất lượng được bảo vệ bằng evidence, không bằng metadata cứng:

1. Plan Review trước Gate 1.
2. Task có acceptance criteria kiểm chứng được.
3. Formatter/linter/typecheck nếu project có cấu hình.
4. Focused unit/integration test cho phần thay đổi.
5. Full regression phù hợp với rủi ro.
6. Build/package check nếu có.
7. Task Review sau test PASS.
8. Integration Test + Integration Review trước Gate 2.
9. Báo cáo ghi command, exit code, output summary và check chưa chạy.

Không được xóa/disable test chỉ để đạt green. Sửa test được phép khi behavior
mong đợi đã thay đổi hợp lệ, nhưng phải có review và evidence thay thế.

Fix cap ba vòng là ngưỡng hỏi user/replan, không phải trạng thái khóa chết. Sau
ba vòng, Director trình bày nguyên nhân và lựa chọn; quyết định của user có thể
tiếp tục vòng mới, đổi model/agent, sửa scope, replan, waive hoặc dừng.

## Failure và recovery

Policy này áp dụng theo loại sự cố, không theo task ID, fixture hoặc framework.
Không được thêm ngoại lệ chỉ để một project test cụ thể PASS.

### Mức bằng chứng tương xứng

- Không tự phát minh yêu cầu external seal, compliance, production hardening
  hoặc optional tool nếu scope/project không yêu cầu.
- Plan Review gom routine findings thành một lượt sửa. Chỉ review lại khi còn
  lỗi material về acceptance, security, data hoặc architecture.
- Missing optional tooling là `N/A` hoặc `INCONCLUSIVE`, không phải source fail.
- Child fail là lane fail có thể phục hồi, không mặc định là project fail.

### Lỗi vận hành

Ví dụ: gateway 502, provider rate limit, UI cancel, child session mất, timeout.

Xử lý:

- retry có backoff và giới hạn chống storm;
- dùng fallback model nếu user đã cấu hình;
- child mất sau restart được đánh dấu stopped/unreconciled;
- re-dispatch từ checkpoint khi an toàn;
- không chuyển project sang block vĩnh viễn.

Nếu provider/tool hoạt động lại, Director tiếp tục từ TODO, child session,
workspace diff và checkpoint hiện có; không tạo lại Brief/Plan và không chạy lại
phần đã có evidence PASS.

### Lỗi source

Build/test/review fail được route qua Test/Review -> Fix -> Retest -> Review.
Evidence thất bại phải được truyền cho BX Fix.

### Cần quyết định user

Director hỏi trực tiếp trong parent chat, đưa evidence và các lựa chọn. Khi user
trả lời, workflow cập nhật artifact/checkpoint và tiếp tục. Không có thao tác
recovery CLI hoặc state edit.

### Restart semantics

Resume không được hiểu là chắc chắn tiếp tục đúng process cũ:

```text
OpenCode/Slim restart
  -> đọc live child/session status
  -> child còn busy: tiếp tục theo dõi
  -> terminal result có sẵn: reconcile
  -> child idle/mất nhưng chưa có terminal result: stopped/unreconciled
  -> kiểm tra partial diff/evidence
  -> re-dispatch task từ CHECKPOINT nếu an toàn
```

### Writer conflict

- Task khác subsystem hoặc ownership không giao nhau được chạy song song.
- Khi phát hiện overlap thực tế, Director tuần tự hóa các writer còn lại hoặc
  dùng worktree nếu project đã hỗ trợ.
- File cần thiết phát sinh ngoài danh sách dự kiến được mở rộng scope minh bạch;
  không coi đây là contract failure nếu không có writer conflict.
- Không tạo lock/WIP counter/job-state BIEXCE để giải quyết conflict.

## UX mục tiêu

### Daily assistant

User chọn agent và hỏi bình thường. Agent có thể gọi specialist nếu permission
và task phù hợp.

### Autopilot project

Trong project:

1. Chọn `BX Director`.
2. Chạy `/bx-auto <yêu cầu>`.
3. Trả lời câu hỏi làm rõ nếu có.
4. Duyệt Gate 1 và Gate 2 trong chat/UI.

Không cần:

- `biexce auto on`;
- gọi `biexce_drive` lặp lại;
- `resolve`/`clear`;
- sửa JSON;
- gọi từng agent thủ công.

## Liên kết tiếp theo

- [Kiến trúc đích và workflow](TARGET-ARCHITECTURE.md)
- [Kế hoạch migration](MIGRATION.md)
- [Acceptance bắt buộc](ACCEPTANCE.md)
