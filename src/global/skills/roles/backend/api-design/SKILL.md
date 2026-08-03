---
name: api-design
description: Implement or revise an HTTP API from an approved contract with correct semantics, validation, authorization, failure handling, and observability. Apply when bx-code or bx-fix changes backend endpoints.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-code, bx-fix, bx-review
  sources: RFC 9110 HTTP Semantics; RFC 9457 Problem Details; OpenAPI Specification; OWASP API Security Top 10 2023
---

# API design

## Khi nào dùng

Dùng khi hiện thực endpoint hoặc sửa hành vi public/internal HTTP boundary. Nếu contract chưa chốt hoặc thay đổi breaking, chuyển về bx-plan/api-contract trước khi code.

## Nội dung

1. Đọc contract, caller, auth middleware, error convention và test hiện có trước khi sửa.
2. Giữ handler mỏng: parse/validate ở boundary, gọi domain/service, map kết quả sang HTTP.
3. Kiểm tra input theo allow-list/schema; giới hạn kích thước, range, format và unknown fields theo contract.
4. Thực hiện authentication trước, authorization theo actor + action + object; mặc định deny và không dựa vào ID khó đoán.
5. Dùng method/status/header đúng semantics; phân biệt client error, conflict, validation, auth và server failure.
6. Giữ transaction ở use-case boundary; xử lý concurrency/idempotency cho operation có thể retry hoặc tạo side effect.
7. Đặt timeout cho dependency; retry chỉ lỗi transient, có giới hạn và chỉ khi operation an toàn/idempotent.
8. Log có cấu trúc với request/correlation ID; metrics/traces phản ánh latency, error, dependency nhưng không chứa secret/PII.
9. Cập nhật contract examples và tests: happy, validation, unauthorized/forbidden, not found/conflict, dependency failure.

Ví dụ ngắn:

```text
POST /runs + Idempotency-Key
validate -> authorize owner -> create in transaction -> 202
same key/same payload -> same result; same key/different payload -> 409
```

## Chống chỉ định / giới hạn

- Không đổi API contract ngầm trong implementation.
- Không catch mọi exception rồi trả 200/400; map lỗi có chủ đích và giữ lỗi không biết thành 5xx.
- Không log credential, token, raw personal payload hoặc internal stack ra response.
