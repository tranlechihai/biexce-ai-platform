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
| `bx-test` | Build, test, evidence và verdict | Không tự sửa lỗi source |
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
→ Integration Test → Integration Review → Human Gate 2 → Complete
```

Workflow chạy tuần tự với WIP=1. Mỗi task có tối đa ba vòng fix; kế hoạch có
tối đa hai vòng revision. Runtime metadata là nguồn quyết định agent, task và
phase kế tiếp.

Bật hoặc dừng Autopilot tại thư mục dự án:

```text
biexce auto on
biexce auto off
```

Human Gate được xử lý trong OpenCode Desktop hoặc TUI. Xem
[CONTROL-QUICKSTART.md](CONTROL-QUICKSTART.md) để biết đầy đủ thao tác.

## Kiểm tra agent và model

1. Khởi động lại OpenCode sau khi cài đặt hoặc đổi model routing.
2. Dùng agent selector trên Desktop hoặc nhấn `Tab` trong TUI.
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
