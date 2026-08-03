---
name: review-verdict
description: Review checklist and verdict standard. Apply when BX Review red-teams a Master Plan or reviews a diff, and when BX Director interprets review results.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-review, bx-director
  sources: harness 0.3.x review contract; oh-my-openagent hyperplan (red-team, bản rút gọn); VoltAgent code-reviewer (chưng cất)
---

# Review Verdict

## A. Red-team Master Plan (trước GATE 1)

Checklist tấn công — mỗi mục trả lời đạt/không kèm bằng chứng:

1. Mỗi task có đủ 4 phần theo `task-spec`? Acceptance kiểm chứng được?
2. Task nào quá to (không vừa một review) hoặc không độc lập?
3. DAG: phụ thuộc thiếu/vòng? Thứ tự có chặn pipeline không?
4. Phạm vi khớp PROJECT_BRIEF? Có scope creep?
5. Dữ liệu/bảo mật: auth, secrets, dữ liệu nhạy cảm được xử lý ở task nào?
6. Lệnh build/test trong plan có nguồn (repo/Brief) hay bịa?
7. Rủi ro tích hợp và rollback có được nêu?

Verdict: `PLAN OK` | `PLAN NEEDS REVISION` + findings đánh số
(severity, lý do, hướng sửa). Không tự viết lại plan.

## B. Review diff (mỗi task, và review tổng B4)

Thứ tự ưu tiên: (1) sai acceptance criterion; (2) regression/edge case/error
handling; (3) security — secrets, injection, authz, dữ liệu lộ; (4) đúng
allowed-files? file lạ/generated lọt vào?; (5) evidence của BX Test có thật
và đủ? (diff không evidence ⇒ không APPROVE trừ khi director waive rõ ràng);
(6) maintainability trọng yếu (trùng lặp lớn, phá kiến trúc).

Finding format: `[Blocker|Major|Minor] <file:line> — <bằng chứng> — <tác
động> — <hướng sửa ngắn>`. Không bịa finding cho đủ mục, không khen.

Verdict: `APPROVE` | `APPROVE WITH MINOR NOTES` | `CHANGES REQUIRED`
(Blocker hoặc criterion không đạt ⇒ luôn CHANGES REQUIRED).
Director quy ước: CHANGES REQUIRED tính là một vòng fix của task.
