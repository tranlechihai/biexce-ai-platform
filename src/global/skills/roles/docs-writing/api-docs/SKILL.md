---
name: api-docs
description: Document versioned APIs with executable contracts, authentication, errors, examples, and compatibility notes. Apply when an endpoint or integration boundary is introduced or changed.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-code, bx-plan, bx-review
  sources: OpenAPI Specification; RFC 9110 HTTP Semantics; RFC 9457 Problem Details; Diataxis reference guidance
---

# API documentation

## Khi nào dùng

Dùng cho HTTP/event/SDK boundary. Tài liệu phải khớp implementation và contract đã duyệt; ưu tiên machine-readable spec làm source of truth khi dự án có.

## Nội dung

1. Nêu base/version, auth, content type, idempotency/rate limit và môi trường áp dụng.
2. Mỗi operation có mục đích, method/path hoặc event name, quyền cần thiết và side effect.
3. Mô tả parameter/body/response bằng type, required, constraint, default và semantic—not chỉ ví dụ.
4. Dùng status code đúng HTTP semantics; error format ổn định với code máy đọc, message an toàn và correlation khi có.
5. Ví dụ request/response hợp lệ, copy được, dùng placeholder/redacted data; thêm ví dụ lỗi quan trọng.
6. Ghi pagination/filter/sort/timezone/encoding và concurrency/precondition behavior nếu liên quan.
7. Nêu backward compatibility, deprecation và migration cho breaking change.
8. Validate OpenAPI/schema và contract test; cập nhật docs trong cùng task với code.

Ví dụ: `POST /orders` ghi auth scope, idempotency key, schema, 201 response và 409 problem detail cho duplicate request.

## Chống chỉ định / giới hạn

- Không document endpoint/field chưa tồn tại như đã hỗ trợ.
- Không dùng secret, token hoặc dữ liệu production trong ví dụ.
- Không thay quyết định API; inconsistency phải route về owner contract/plan.
