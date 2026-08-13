# Hướng dẫn sử dụng agent BIEXCE

Mỗi agent BIEXCE là một role contract của OpenCode, gồm hướng dẫn, quyền hạn và
các skill tùy chọn. File agent không khóa cứng model; người dùng có thể gán bất
kỳ `provider/model` đã kết nối thông qua BIEXCE CLI.

## Vai trò

| Agent | Phù hợp với | Giới hạn |
| --- | --- | --- |
| `bx-director` | Điều phối Autopilot, workflow state và Human Gate | Không trực tiếp sửa source |
| `bx-explore` | Khảo sát repository và tạo Codebase Brief | Source chỉ đọc; chỉ được ghi Brief do hệ thống quản lý |
| `bx-plan` | Yêu cầu, kiến trúc, kế hoạch và task contract | Không triển khai source |
| `bx-code` | Feature task đã duyệt và focused test | Không tự mở rộng phạm vi hoặc review công việc của mình |
| `bx-fix` | Phân tích root cause và sửa lỗi tối thiểu từ evidence | Không thêm feature không liên quan |
| `bx-test` | Build, test, evidence và verdict | Không sửa source/test; chỉ được ghi evidence được giao dưới `.biexce/reports/**` |
| `bx-review` | Review kế hoạch, thay đổi và tích hợp | Không sửa source đang review |

Cả 7 vai trò đều bị chặn static delegation. Trong Autopilot, chỉ `Bx-Director`
được cấp tool `biexce_delegate` có runtime guard, và chỉ khi project state cho
phép bước workflow kế tiếp.

## Skill

Skill được tổ chức trong `src/global/skills`:

- `core`: task, evidence, state và delivery contract dùng chung.
- `roles`: skill kỹ thuật có thể tái sử dụng, nhóm theo chuyên môn.
- `company`: policy và knowledge riêng của tổ chức.

Role skill bao phủ planning, architecture, backend, QA, frontend, Android,
iOS, Unity, DevOps, security, documentation và data/AI. Skill tùy chọn
`qa-testing/browser-exploratory` chỉ được dùng khi acceptance cần thao tác trên
browser; skill này không thay thế regression test có tính xác định.

Các file có trạng thái `draft` hoặc `skeleton` chưa phải nguồn quy định chính
thức. Đặc biệt, convention và Git policy của công ty phải được tổ chức cung
cấp và phê duyệt trước khi agent dựa vào chúng.

Xem [AGENT-SKILL-CATALOG.md](AGENT-SKILL-CATALOG.md) để biết danh mục chuẩn.

## Hỗ trợ hằng ngày

Chọn trực tiếp agent phụ trách loại công việc cần thực hiện trong OpenCode.
Không cần bật Autopilot. Agent được chọn sẽ tuân theo vai trò của mình và route
công việc ngoài phạm vi thay vì âm thầm đổi vai.

## Autopilot

Chọn `Bx-Director` để chạy workflow nhiều task:

```text
Explore → Plan → Plan Review → Human Gate 1
→ Code → Test → Fix hoặc Task Review → task kế tiếp
→ Integration Test → Integration Fix/Retest → Integration Review
→ Human Gate 2 → Complete
```

Sau khi Director hoàn tất Project Brief, `biexce_drive` tự tạo các child session
Explore, Plan và Plan Review rồi dừng ở Gate 1. Preflight runtime kiểm tra DAG,
`Verify`, toolchain và writable scope trước khi cho phép code. Sau Gate 1,
workflow dùng WIP 1–4 theo plan. Phase read-only độc lập có thể chạy song song
trong model quota; `CODE/FIX` dùng chung working tree được serialize. Mỗi task
có tối đa ba vòng fix; kế
hoạch có tối đa hai vòng revision. Runtime metadata là nguồn quyết định agent,
task và phase kế tiếp.

Trong từng task, `Bx-Code` triển khai source và test thuộc task rồi tự kiểm tra
theo các gate đang có của project. `Bx-Test` chạy verification độc lập theo thứ
tự format check → lint/static → typecheck → unit/focused →
integration/contract/E2E → build/package. `Bx-Test` không sửa source; khi có
failed check, runtime chuyển sang `Bx-Fix` và sau đó bắt buộc quay lại `Bx-Test`.
Gate không áp dụng phải ghi `N/A` có lý do; gate bắt buộc không chạy được là
`INCONCLUSIVE`, không phải PASS. Runtime thử lại mà không tăng fix round;
profile thường giữ state có thể tiếp tục và chuyển `PAUSED` khi hết retry,
profile `critical` mới block theo contract nghiêm ngặt.

Trong `standard`/`fast`, Code/Fix có thể tạo thêm file source hợp lệ trong mục
tiêu đã duyệt dù Plan chưa liệt kê đủ. Runtime vẫn cấm `.biexce`, Git,
secret/credential, path ngoài project và path thuộc task song song. Khi
Integration Test hoặc Integration Review phát hiện lỗi, runtime tự gọi Bx-Fix
rồi retest; human không phải dispatch agent hay sửa state.

Nếu BX Code kết thúc bằng `FAILED` và kèm failed check xác định, runtime hoàn
tất job CODE đó rồi chuyển task sang BX Fix; không gọi lại cùng job CODE. Với
`standard`/`fast`, BX Fix được phép sửa tối thiểu source hoặc test trong project
khi evidence chứng minh acceptance đã duyệt thay thế một expectation cũ. Coverage
còn hợp lệ phải được giữ lại; cấm xóa, skip, disable hoặc làm yếu test chỉ để lấy
PASS. Profile `critical` vẫn yêu cầu sửa Plan/scope hoặc human decision khi có
xung đột phạm vi.

Khi nâng runtime giữa một project đang chạy, driver nhận diện state lịch sử có
job writer `COMPLETED` nhưng `result_status=FAILED`. Nếu người dùng yêu cầu
`standard`/`fast`, runtime phục hồi task đó sang FIX ngay trong cùng lượt drive,
tăng một fix round và ghi audit; không yêu cầu chỉnh JSON state hoặc gọi lại
CODE. Evidence thiếu hoặc protected path vẫn không được tự phục hồi. Với
profile `standard`/`fast`, task có bằng chứng `TEST FAIL` hoặc
`REVIEW CHANGES_REQUIRED` sau ba vòng fix được cấp đúng một vòng adjudication
có audit (`BX Fix -> BX Test -> BX Review`); nếu vòng này vẫn fail thì task
block thật và không được tự mở lại.

Nếu blocker cũ chỉ còn thông báo chung ở task nhưng lỗi scope chi tiết nằm trong
job history, runtime vẫn nhận diện được. Với file source/test thông thường của
CODE/FIX, nó chạy lại BX Test trên workspace thật; FAIL mới chuyển BX Fix rồi
retest, còn PASS tiếp tục Review. Đây là rule chung, không đặc cách task ID.

Bật hoặc dừng Autopilot tại thư mục dự án:

```text
biexce auto on
biexce auto off
```

Human Gate được xử lý trong OpenCode TUI hoặc OpenChamber. Xem
[CONTROL-QUICKSTART.md](CONTROL-QUICKSTART.md) để biết đầy đủ thao tác.

## Kiểm tra agent và model

1. Khởi động lại OpenCode sau khi cài đặt hoặc đổi model routing.
2. Dùng agent selector trên OpenChamber hoặc nhấn `Tab` trong OpenCode TUI.
3. Xác nhận agent và model thực tế trong composer hoặc response.
4. Dùng `biexce status` để so sánh với routing đã cấu hình.
5. Dùng `biexce self-test` để kiểm tra control plane và
   `biexce self-test --live-inference` khi endpoint truy cập được.

Routing đã cấu hình và model được response live báo cáo là hai evidence riêng;
cần kiểm tra cả hai khi xác nhận một máy đã được thiết lập đúng.

## Chính sách dữ liệu

Việc chọn model không làm thay đổi quyền dữ liệu. Source, diff, credential và
dữ liệu production nhạy cảm vẫn phải tuân theo security policy của tổ chức.
Chỉ được dùng cloud khi provider đã được phê duyệt và nội dung đầu vào an toàn
cho đích đến đó. Xem [AGENT-ROLES.md](AGENT-ROLES.md) để biết quy tắc ưu tiên,
routing và escalation.

Ngoại lệ được hỗ trợ: khi user chủ động gắn cloud model cho `bx-review`, agent
này được đọc raw scoped diff và lượng source tối thiểu cần thiết ở
`TASK_REVIEW`/`INTEGRATION_REVIEW`. Quyền vẫn tuyệt đối read-only; secret,
credential, signing material, dữ liệu production nhạy cảm và file ngoài project
vẫn bị cấm. `PLAN_REVIEW` chỉ dùng Brief/Plan/task artifacts.
