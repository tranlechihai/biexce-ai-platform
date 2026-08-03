---
name: testing-backend
description: Build a risk-based backend test set across domain, persistence, contract, security, and failure boundaries. Apply when bx-code, bx-fix, or bx-test validates backend behavior.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-code, bx-fix, bx-test, bx-review
  sources: Martin Fowler practical test pyramid; Cucumber Gherkin reference; OWASP ASVS 5.0
---

# Testing backend

## Khi nào dùng

Dùng khi backend behavior thay đổi hoặc bug cần regression. Chọn tầng thấp nhất chứng minh được rủi ro; thêm integration/contract/E2E chỉ cho boundary mà unit test không chứng minh.

## Nội dung

1. Map `acceptance/risk -> test -> command -> evidence`; ưu tiên auth, data integrity, concurrency và failure path.
2. Unit test domain rule bằng public behavior, không khóa test vào private implementation.
3. Integration test repository/database với engine hoặc semantics đủ giống production; kiểm tra constraint, transaction và migration.
4. Contract/API test request/response schema, status/error, auth và compatibility.
5. Test dependency failure: timeout, malformed response, retry/idempotency và partial failure.
6. Dùng Arrange–Act–Assert hoặc Given–When–Then; mỗi test có lý do thất bại rõ và dữ liệu tối thiểu.
7. Kiểm soát clock, randomness, network, database và parallel state; fixture độc lập, cleanup xác định.
8. Chạy focused tests trước, rồi suite bị ảnh hưởng; ghi exact command, exit code và skipped/known failures.

Ví dụ ngắn:

```text
Risk: hai retry tạo hai Run.
Test: gửi cùng idempotency key song song; assert một record và response nhất quán.
Evidence: command + test name + database count.
```

## Chống chỉ định / giới hạn

- Không mock chính behavior đang cần chứng minh.
- Không dùng coverage percentage làm bằng chứng duy nhất; test phải bám risk/acceptance.
- Không bỏ test flaky qua retry vô hạn; cô lập nguyên nhân hoặc quarantine có owner và hạn xử lý.
