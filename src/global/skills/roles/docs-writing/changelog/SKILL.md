---
name: changelog
description: Maintain a human-readable changelog organized by impact, release state, and compatibility. Apply when shipping or summarizing user-visible changes.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-director, bx-code, bx-review
  sources: Keep a Changelog 2.0.0; Semantic Versioning 2.0.0; CommonMark specification
---

# Changelog

## Khi nào dùng

Dùng khi behavior, interface, setup, security hoặc compatibility thay đổi. Changelog phục vụ người dùng/operator; commit log và danh sách file không phải nội dung thay thế.

## Nội dung

1. Giữ `Unreleased` ở đầu; release có version và ngày ISO, link compare nếu repo hỗ trợ.
2. Nhóm theo Added, Changed, Deprecated, Removed, Fixed, Security; chỉ dùng nhóm có nội dung.
3. Mỗi entry nói tác động quan sát được và đối tượng bị ảnh hưởng, không chỉ tên ticket/file.
4. Breaking change nêu rõ migration/action; deprecation có replacement và timeline nếu đã quyết định.
5. Security entry tránh chi tiết khai thác/secret; link advisory theo policy.
6. Gộp thay đổi kỹ thuật nội bộ không ảnh hưởng user; không lặp cùng một việc dưới nhiều nhóm.
7. Versioning theo policy dự án; không tự phát hành hoặc tự quyết major/minor/patch khi chưa được giao.
8. Đối chiếu release scope, docs và test evidence trước khi ghi “fixed” hoặc “supported”.

Ví dụ: `Fixed — Model routing now recognizes native agent bindings during offline validation, allowing an already-applied seven-agent setup to arm.`

## Chống chỉ định / giới hạn

- Không paste commit history hoặc mọi refactor nội bộ.
- Không ghi ngày/version/release đã hoàn tất nếu mới ở kế hoạch.
- Không xóa lịch sử cũ khi chuẩn hóa format trừ khi task yêu cầu migration riêng.
