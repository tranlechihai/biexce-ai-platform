---
name: design-discovery
description: Làm rõ mục tiêu, ràng buộc và phương án thiết kế trước thay đổi không tầm thường; chỉ áp dụng khi yêu cầu còn mơ hồ hoặc có quyết định kiến trúc đáng kể.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-director, bx-plan, bx-explore, bx-review
  sources: obra/superpowers brainstorming; BIEXCE task-spec and Human Gate policy
---

# Design Discovery

## Khi nào dùng

Dùng trước plan khi yêu cầu có nhiều cách hiểu, ảnh hưởng từ ba hệ thống trở lên,
thay đổi contract/data/security, hoặc cần chọn kiến trúc. Không dùng cho câu hỏi,
bug đã có reproduction, hay thay đổi nhỏ có objective và acceptance rõ ràng.

## Quy trình

1. Đọc context tối thiểu: brief, code liên quan, constraint và trạng thái hiện tại.
2. Tóm tắt một lần: mục tiêu, người dùng, in-scope, out-of-scope, tiêu chí thành công.
3. Gom các điểm chưa rõ thành ít câu hỏi có tác động quyết định; không phỏng vấn kéo dài.
4. Đề xuất 2–3 phương án khi thật sự có trade-off, nêu lựa chọn khuyến nghị và lý do.
5. Chốt thiết kế theo phần nhỏ: luồng, component, dữ liệu, lỗi, test và rollout.
6. Chuyển quyết định đã duyệt thành task contract; không để agent sau phải đoán lại.

User có thể yêu cầu “chọn mặc định hợp lý”. Khi đó ghi rõ assumption có thể đảo ngược
và tiếp tục; chỉ dừng ở Human Gate nếu quyết định ảnh hưởng source/kiến trúc đáng kể.

## Output tối thiểu

```markdown
Mục tiêu: <kết quả quan sát được>
Ràng buộc: <platform, data, performance, compatibility>
Quyết định: <phương án đã chọn và lý do>
Luồng chính: <input -> xử lý -> output>
Rủi ro/test: <rủi ro chính và cách kiểm chứng>
Open decisions: <none hoặc câu hỏi thật sự cần human>
```

## Giới hạn

- Không biến brainstorming thành một workflow authority thứ hai.
- Không yêu cầu duyệt thiết kế cho task nhỏ ở profile `fast`.
- Không tự mở rộng scope, tự chọn yêu cầu sản phẩm quan trọng, hoặc code trước khi
  quyết định bắt buộc đã được chốt.
