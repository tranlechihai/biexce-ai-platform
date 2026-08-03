---
name: prd
description: Build a traceable product requirements document from a validated request. Apply when bx-plan or bx-director must define outcomes, scope, users, constraints, and acceptance before architecture or implementation.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-plan, bx-director
  sources: BMAD-METHOD workflow map; GitHub Spec Kit specification workflow
---

# PRD

## Khi nào dùng

Dùng khi yêu cầu còn ở mức ý tưởng, nhiều bên hiểu khác nhau, hoặc thay đổi có ảnh hưởng đến nhiều hệ thống. Với bug nhỏ hay task đã có acceptance criteria rõ, dùng task spec thay vì tạo PRD mới.

## Nội dung

1. Xác nhận đầu vào: vấn đề, người dùng, bối cảnh, mục tiêu kinh doanh, deadline/ràng buộc đã được người có thẩm quyền chốt.
2. Ghi phần **Outcome** bằng kết quả quan sát được; tách outcome khỏi giải pháp kỹ thuật.
3. Viết PRD theo cấu trúc:
   - `Problem / Context`
   - `Users and jobs`
   - `Goals` và tín hiệu đo thành công
   - `In scope` / `Out of scope`
   - hành vi chính và user journey
   - yêu cầu chức năng có ID ổn định `REQ-*`
   - yêu cầu chất lượng: bảo mật, dữ liệu, hiệu năng, khả dụng, tương thích
   - ràng buộc, phụ thuộc, giả định
   - rủi ro và câu hỏi mở, mỗi mục có owner
   - tiêu chí nghiệm thu cấp sản phẩm
4. Tách mỗi yêu cầu thành lát cắt có thể kiểm chứng; ghi quan hệ phụ thuộc thay vì dựa vào thứ tự dòng.
5. Lập trace `Goal -> REQ -> story/task -> test/evidence` để tránh yêu cầu mồ côi.
6. Chỉ chuyển sang kiến trúc khi các mục chưa rõ có ảnh hưởng lớn đã được chốt hoặc được đánh dấu rõ là blocker.

Ví dụ ngắn:

```text
Goal G-01: giảm thao tác tạo phiên làm việc hằng ngày.
REQ-03: người dùng khởi tạo daily assist bằng một lệnh.
Success: phiên tạo ra plan và evidence beacon đúng schema đã duyệt.
Out of scope: tự động merge hoặc deploy.
```

## Chống chỉ định / giới hạn

- Không bịa KPI, deadline, persona hoặc nhu cầu người dùng.
- Không khóa framework/database khi PRD chỉ cần mô tả outcome; quyết định kỹ thuật thuộc architecture/ADR.
- Không coi câu hỏi mở là đã chốt. Escalate nếu nó làm thay đổi scope, security zone hoặc acceptance.
