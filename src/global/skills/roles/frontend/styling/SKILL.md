---
name: styling
description: Implement responsive, maintainable frontend styling that follows the existing design system and preserves accessible interaction states. Apply when a task changes layout or visual presentation.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-code, bx-review
  sources: MDN responsive design and CSS layout guidance; W3C WCAG 2.2; web.dev responsive design guidance
---

# Styling

## Khi nào dùng

Dùng khi chỉnh CSS, layout, theme, responsive behavior hoặc design token. Kiểm tra cách dự án đang style trước; giữ nguyên hệ thống hiện tại nếu task không yêu cầu migration.

## Nội dung

1. Dùng token/variable có sẵn cho màu, spacing, typography, radius và layer; tránh magic value lặp lại.
2. Layout theo content và container; ưu tiên Flexbox/Grid, tránh tọa độ tuyệt đối cho cấu trúc chính.
3. Mobile-first: mặc định cho viewport nhỏ, mở rộng bằng breakpoint có lý do từ nội dung.
4. Giữ target chạm đủ lớn, không phụ thuộc hover, và kiểm tra text zoom/reflow.
5. Bảo toàn `focus-visible`, disabled, error, loading và reduced-motion; màu không phải tín hiệu duy nhất.
6. Scope style theo convention dự án; tránh selector quá sâu, `!important` hoặc global override ngoài phạm vi.
7. Hạn chế layout shift; đặt kích thước/aspect-ratio cho media và tránh animation thuộc tính gây layout.
8. Kiểm viewport nhỏ/lớn, keyboard focus và theme hiện có; ghi rõ visual check chưa chạy nếu cần.

Ví dụ: card dùng grid tự co, token spacing/màu, `:focus-visible`, và breakpoint khi nội dung bắt đầu tràn.

## Chống chỉ định / giới hạn

- Không đổi palette, font, framework CSS hoặc kiến trúc design system ngoài scope.
- Không “pixel-perfect” một ảnh tham chiếu bằng cách phá responsive behavior.
- Không ẩn nội dung quan trọng trên mobile chỉ để layout gọn hơn.
