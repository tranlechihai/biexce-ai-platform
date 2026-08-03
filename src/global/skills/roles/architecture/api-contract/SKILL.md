---
name: api-contract
description: Define a versioned, testable API boundary before implementation, including errors, security, compatibility, and examples. Apply when bx-plan designs or reviews communication between independently changing components.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-plan, bx-review
  sources: OpenAPI Specification; RFC 9110 HTTP Semantics; RFC 9457 Problem Details; OWASP API Security Top 10 2023
---

# API contract

## Khi nào dùng

Dùng cho HTTP API mới/thay đổi, internal service boundary, webhook hoặc contract mà producer/consumer có thể phát triển độc lập. Với function nội bộ cùng module, ưu tiên type/interface và test tại codebase.

## Nội dung

1. Chọn format/version được repo và toolchain hỗ trợ; với HTTP dùng OpenAPI làm contract machine-readable khi phù hợp.
2. Mô tả từng operation: method/path, intent, auth scope, parameters, request body, success response, errors và examples.
3. Dùng HTTP method/status/cache/precondition đúng semantics; không trả `200` cho mọi kết quả.
4. Định nghĩa schema chặt: required/nullability, enum/format, bounds, unknown fields và content type.
5. Chuẩn hóa lỗi; ưu tiên `application/problem+json` khi tương thích. Không lộ stack trace, query, secret hay policy nội bộ.
6. Chốt pagination/filter/sort, idempotency, concurrency, timeout/retry và rate/resource limits nếu operation cần.
7. Phân tích object/function-level authorization, dữ liệu nhạy cảm và trust với upstream API.
8. Ghi compatibility policy: thay đổi additive, deprecation window, breaking change/versioning; tạo contract tests cho producer và consumer.

Ví dụ ngắn:

```yaml
POST /runs:
  security: [workstation:run]
  responses:
    '202': {description: Accepted}
    '409': {description: Duplicate idempotency key}
    '422': {description: Validation problem}
```

## Chống chỉ định / giới hạn

- Không thiết kế contract chỉ từ database table hoặc framework DTO.
- Không thêm version vào URL/header theo thói quen nếu chưa có compatibility policy.
- Không tuyên bố “OpenAPI valid” nếu chưa lint/parse bằng tool version của repo.
