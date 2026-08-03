---
name: regression
description: Build and run a change-focused regression set with explicit impact analysis, stable gates, and failure classification. Apply when bx-test verifies a fix, release candidate, dependency update, or shared contract change.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-test, bx-fix, bx-review
  sources: Martin Fowler practical test pyramid; pytest flaky-test guidance; BIEXCE evidence format
---

# Regression

## Khi nào dùng

Dùng sau bug fix, refactor, dependency/config/schema/contract change và trước package/release. Mức regression tăng theo blast radius, không mặc định chạy mọi test vô điều kiện.

## Nội dung

1. Xác định changed behavior, caller/consumer, shared contract, data/migration, platform và failure đã sửa.
2. Thêm test tái hiện bug trước hoặc cùng fix; test phải fail vì nguyên nhân cũ và pass với fix.
3. Chọn suite theo vòng:
   - focused test của behavior;
   - module/component và direct dependents;
   - contract/integration cho boundary bị đổi;
   - smoke/E2E và full suite cho release hoặc blast radius rộng.
4. Với dependency/toolchain update, chạy compatibility matrix được support và package/install smoke.
5. Ghi exact commands, version/environment, exit code, test counts, duration và skipped.
6. Phân loại failure; không gộp pre-existing/environment vào patch failure nhưng vẫn báo rõ.
7. Flaky test là defect: thu evidence, cô lập state/time/order; quarantine chỉ khi có owner, lý do và điều kiện gỡ.

Ví dụ ngắn:

```text
Fix: manifest bỏ hardcode 4 agent.
Regression: generator --check -> unit hashes -> Windows/Linux install ->
OpenCode discovery -> package verifier.
```

## Chống chỉ định / giới hạn

- Không sửa expected output chỉ để test xanh khi contract chưa đổi.
- Không dùng rerun thành tiêu chí pass cho test flaky.
- Không tuyên bố “không regression” nếu chỉ chạy focused test mà không đánh giá dependents.
