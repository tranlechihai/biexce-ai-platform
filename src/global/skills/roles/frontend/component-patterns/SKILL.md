---
name: component-patterns
description: Build small, accessible frontend components with explicit data flow, stable public APIs, and testable behavior. Apply when implementing or reviewing user-interface components.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-code, bx-review
  sources: React official documentation on purity and sharing state; W3C WAI accessible component guidance; Testing Library guiding principles
---

# Component patterns

## Khi nào dùng

Dùng khi tạo, tách hoặc review component UI. Trước khi áp dụng, đọc framework, design system và convention hiện có; ưu tiên khớp codebase hơn việc đưa thêm abstraction.

## Nội dung

1. Mỗi component có một trách nhiệm quan sát được; tách khi phần con có lifecycle, state hoặc khả năng tái sử dụng riêng, không tách chỉ để giảm số dòng.
2. Giữ render thuần: cùng props/state cho cùng kết quả; side effect nằm trong event handler hoặc lifecycle phù hợp.
3. Dữ liệu đi xuống qua props, sự kiện đi lên qua callback; đặt state ở owner chung gần nhất và tránh hai nguồn sự thật.
4. Public API nhỏ, có tên theo domain; tránh boolean chồng chéo nếu một variant rõ hơn.
5. Ưu tiên composition và children/slots trước inheritance hoặc component tổng quát quá sớm.
6. Giữ semantic HTML, label, keyboard path và focus behavior trong contract của component.
7. Tách fetch/cache/global state khỏi presentational component khi ranh giới đó giúp test.
8. Test hành vi người dùng và output truy cập được; không khóa test vào state nội bộ.

Ví dụ: `SaveButton` nhận `disabled`, `onSave`, hiển thị trạng thái submit và giữ accessible name; form cha sở hữu dữ liệu và xử lý request.

## Chống chỉ định / giới hạn

- Không dựng design system, state library hoặc generic wrapper mới nếu task không yêu cầu.
- Không di chuyển state chỉ để “đúng pattern” khi component hiện tại nhỏ và rõ.
- Không thay semantic element bằng `div` kèm click nếu button/link gốc đáp ứng được.
