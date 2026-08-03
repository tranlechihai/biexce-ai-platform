---
name: accessibility
description: Enforce an actionable WCAG 2.2 accessibility baseline for user-facing interfaces. Apply during implementation, testing, or review of interactive UI.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-code, bx-test, bx-review
  sources: W3C Web Content Accessibility Guidelines 2.2; WAI-ARIA Authoring Practices Guide; HTML Living Standard
---

# Accessibility

## Khi nào dùng

Dùng cho mọi UI người dùng, đặc biệt form, modal, menu, navigation, media và trạng thái động. Mục tiêu mặc định là WCAG 2.2 AA khi sản phẩm không quy định mức khác.

## Nội dung

1. Dùng HTML semantic và control native trước ARIA; ARIA không bổ sung hành vi keyboard tự động.
2. Mọi control có accessible name; label mô tả mục đích, error liên kết với field, instruction không chỉ là placeholder.
3. Toàn bộ luồng hoạt động bằng keyboard, thứ tự focus logic, không keyboard trap; modal quản lý focus đúng.
4. Contrast, reflow, zoom, target size và focus appearance đáp ứng mức đã chọn; không truyền nghĩa chỉ bằng màu.
5. Ảnh có alt theo mục đích; ảnh trang trí alt rỗng; heading và landmark tạo cấu trúc hợp lý.
6. Trạng thái động cập nhật cho assistive technology bằng live region khi cần, không spam thông báo.
7. Tôn trọng reduced motion và không dùng chuyển động nhấp nháy nguy hiểm.
8. Kiểm tự động chỉ là lớp đầu; thêm keyboard test và screen-reader check cho luồng quan trọng.

Ví dụ: dialog có title được liên kết, focus đặt vào control đầu, `Escape` đóng, focus trả về trigger và nền không nhận tab.

## Chống chỉ định / giới hạn

- Không thêm ARIA role khi element native đã có semantics đúng.
- Không tuyên bố “accessible” chỉ dựa trên lint/axe pass.
- Không tự bỏ yêu cầu accessibility vì UI nội bộ; cần waiver được ghi nhận nếu có ngoại lệ.
