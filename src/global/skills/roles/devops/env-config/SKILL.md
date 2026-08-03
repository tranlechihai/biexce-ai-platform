---
name: env-config
description: Define portable environment configuration without committing secrets, with validation, safe examples, and explicit precedence. Apply when code or tooling consumes runtime configuration.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-code, bx-fix, bx-review
  sources: Twelve-Factor App Config guidance; OWASP Secrets Management Cheat Sheet; BIEXCE Zone A/B/C security policy
---

# Environment configuration

## Khi nào dùng

Dùng khi thêm/sửa environment variable, config file, endpoint hoặc feature flag. Phân loại dữ liệu trước khi chọn nơi lưu và cách log.

## Nội dung

1. Tách config thay đổi theo môi trường khỏi code; tên biến ổn định, có prefix và mô tả mục đích/format.
2. Một precedence rõ: CLI/secret store/environment/config/default; không có hai nguồn thật không kiểm soát.
3. Validate khi startup với lỗi chỉ tên biến và yêu cầu, không echo giá trị nhạy cảm.
4. Commit `.env.example` hoặc schema với placeholder an toàn; `.env` thật nằm trong ignore và secret store.
5. Default chỉ cho giá trị an toàn trong dev; production-sensitive config thiếu phải fail closed.
6. URL/path/duration/boolean được parse typed, normalize cross-platform và không ghép shell string.
7. Rotation/reload behavior được ghi rõ cho credential/flag; log chỉ key/source đã dùng khi an toàn.
8. Test missing, invalid, precedence và redaction; chạy secret scan chuẩn của repo trước bàn giao.

Ví dụ: `APP_API_BASE_URL` có URL validation và default dev; `APP_API_TOKEN` bắt buộc từ secret store, không có default và không log.

## Chống chỉ định / giới hạn

- Không tạo, đọc hoặc commit secret thật để “test config”.
- Không dùng một JSON blob secret nếu từng field có thể quản lý/rotate riêng.
- Không âm thầm fallback sang production endpoint hoặc credential khác khi config sai.
