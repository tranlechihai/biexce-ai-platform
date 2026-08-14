# Kế hoạch migration

[← Tổng quan kiến trúc](OPENCODE-SLIM-BIEXCE.md)

## Giai đoạn 0 — Chốt baseline

- Đóng băng custom scheduler/runtime hiện tại.
- Lưu source và test baseline; không xóa runtime cũ.
- Pin version OpenCode/OpenChamber đang dùng.
- Không cài Slim global nếu chưa có user approval.

Chi tiết version và ranh giới: [Baseline](BASELINE.md).

## Giai đoạn 1 — Prototype tách biệt

- Dùng workspace/config test riêng.
- Pin `oh-my-opencode-slim@2.2.13`, commit
  `781ca04fb83dbcd73a262c19ca70533ebbc117d2`; tắt auto-update.
- Xác minh compatibility giữa OpenCode hiện hành và SDK mà Slim pin; không nâng
  user-global trong prototype nếu chưa có user approval.
- Xác minh OpenCode native background subagents hoạt động.
- Khai báo mapping đủ bảy BIEXCE role.
- Xác minh model cloud/local và permission.
- Xác minh child hiển thị trong OpenChamber.
- Xác minh hai task độc lập chạy song song.
- Xác minh rõ giới hạn restart của bản Slim stable; không xem job board in-memory
  là bằng chứng resume thành công.

Không sửa hoặc xóa runtime production/user-global trong giai đoạn này. Cờ và
compatibility contract của prototype được chốt trong [Baseline](BASELINE.md).

## Giai đoạn 2 — BIEXCE workflow pack trên Slim

- Port prompt bảy role.
- Port lazy skill/knowledge loading.
- Xây `/bx-auto`.
- Xây Project Brief, Plan, task và checkpoint templates.
- Thực hiện Gate 1/Gate 2 qua UI.
- Thực hiện Code/Test/Fix/Review/Integration flow.
- Thực hiện user-decision transition và audit waiver.

Hợp đồng source, CLI cô lập, artifact và `/bx-auto` được mô tả tại
[BIEXCE workflow pack trên Slim](WORKFLOW-PACK.md).

## Giai đoạn 3 — Recovery và parallel acceptance

- Gateway fail/recover.
- Child cancel/timeout/stopped.
- Restart OpenCode/OpenChamber/server.
- Writer conflict và worktree.
- User thay đổi scope giữa workflow.
- Test cũ lỗi thời cần cập nhật.

## Giai đoạn 4 — Loại runtime cũ

Chỉ sau khi Giai đoạn 1–3 PASS:

- xóa custom scheduler/reconciler/supervisor/job board/lease;
- xóa workflow state và recovery schema cũ;
- thu nhỏ `biexce-control.js` thành integration/policy adapter tối thiểu;
- cập nhật CLI theo config Slim;
- xóa test/doc legacy;
- chạy full source regression.

## Giai đoạn 5 — RC acceptance

- đóng gói Windows/Ubuntu/macOS;
- cài sạch trên máy mới;
- chạy acceptance matrix nhiều lần;
- kiểm tra không cần state intervention;
- phát hành RC mới chỉ khi toàn bộ tiêu chí bắt buộc PASS.

## Điều kiện xóa runtime cũ

Không xóa custom runtime chỉ vì prototype chạy một calculator. Bắt buộc:

- đủ bảy role và model routing PASS;
- full workflow đến hai gate PASS;
- restart recovery PASS;
- parallelism/conflict PASS;
- user-decision transition PASS;
- full-stack acceptance PASS;
- source tests và installer tests PASS;
- có rollback bundle của baseline cũ.

Nếu Slim không đáp ứng một tiêu chí bắt buộc, ưu tiên cấu hình/prompt/adapter
mỏng. Không quay lại xây scheduler BIEXCE mới nếu chưa có quyết định kiến trúc
mới của user.

## Deliverables

- cấu hình Slim đã pin version;
- mapping bảy BIEXCE roles;
- per-agent model routing generator;
- `/bx-auto` workflow;
- Gate 1/Gate 2 UI flow;
- skill/knowledge loader;
- checkpoint/resume behavior;
- acceptance fixtures và reports;
- installer/doctor/status cập nhật;
- migration và rollback guide;
- RC bundle cho ba OS sau khi acceptance PASS.

## Liên kết tiếp theo

- [Acceptance, rủi ro và Definition of Done](ACCEPTANCE.md)
- [Kiến trúc đích](TARGET-ARCHITECTURE.md)
