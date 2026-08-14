# Acceptance, rủi ro và Definition of Done

[← Tổng quan kiến trúc](OPENCODE-SLIM-BIEXCE.md)

## Acceptance matrix bắt buộc

1. Greenfield calculator từ đầu đến Gate 2.
2. Project có test cũ cần cập nhật do acceptance mới.
3. Full-stack project nhiều task.
4. Hai read-only agents chạy song song.
5. Hai writers khác subsystem chạy song song.
6. Writer conflict được tuần tự hóa hoặc dùng worktree.
7. Restart giữa task và resume an toàn.
8. Gateway 502 rồi hoạt động lại.
9. Worker/model fail và fallback/re-dispatch.
10. Test -> Fix -> Retest -> Review.
11. User đổi scope/architecture giữa workflow và hệ thống tiếp tục.
12. User waive tiêu chí với audit nhưng evidence vẫn trung thực.
13. OpenChamber hiển thị parent và child đúng role/model/status.
14. Windows và Ubuntu; macOS smoke sau khi hai nền tảng đầu ổn.

Mỗi case phải chạy lại ít nhất hai lần với workspace sạch. Không case nào được
yêu cầu sửa state, clear lock hoặc gọi specialist thủ công.

## Rủi ro và kiểm soát

| Rủi ro | Kiểm soát |
|---|---|
| Phụ thuộc Slim/OpenCode upstream | Pin version/commit, tắt auto-update trong release |
| Slim thay API | Integration tests và compatibility matrix |
| Custom role không map đúng parent | Prototype mapping trước khi port workflow |
| Restart không tự tiếp tục process | Checkpoint + stopped detection + safe re-dispatch |
| Parallel writer conflict | Ownership, tuần tự hóa, worktree có chủ đích |
| Agent sửa test để che lỗi | Review test diff + evidence + full regression |
| User override tạo residual risk | Audit rõ, không đổi FAIL thành PASS |
| Context quá lớn | Lazy skills, scoped knowledge, self-contained child prompt |

## Definition of Done

Refactor chỉ hoàn tất khi user có thể mở một project mới, chạy `/bx-auto`, duyệt
hai gate trong giao diện và nhận source + test + review + final report mà không
phải chữa runtime.

BIEXCE phải nghe quyết định của user, Slim phải điều phối child dựa trên
OpenCode live state, và mọi tuyên bố chất lượng phải có evidence thực tế.

## Điều kiện phát hành

Các case acceptance, điều kiện xóa runtime cũ và deliverables trong
[Kế hoạch migration](MIGRATION.md) đều phải PASS. Một calculator riêng lẻ không
đủ để loại runtime cũ hoặc phát hành RC.

## Liên kết liên quan

- [Baseline](BASELINE.md)
- [Kiến trúc đích](TARGET-ARCHITECTURE.md)
- [Quyền user, quality và vận hành](POLICY-OPERATIONS.md)
- [Kế hoạch migration](MIGRATION.md)
