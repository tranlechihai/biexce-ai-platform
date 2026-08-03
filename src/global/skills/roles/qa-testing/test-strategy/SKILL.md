---
name: test-strategy
description: Create a risk-based test strategy that maps requirements to test levels, environments, data, gates, and evidence. Apply when bx-test plans verification for a feature, release, migration, or high-risk change.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-test, bx-plan, bx-review
  sources: Cucumber Gherkin reference; Martin Fowler practical test pyramid; OWASP ASVS 5.0; BIEXCE evidence format
---

# Test strategy

## Khi nào dùng

Dùng trước triển khai cho thay đổi nhiều rủi ro/boundary, và trước release để chốt coverage/gates. Task nhỏ vẫn cần criteria→check nhưng không nhất thiết có tài liệu strategy riêng.

## Nội dung

1. Xác định scope, out-of-scope, architecture/boundaries, acceptance và Definition of Done.
2. Lập risk inventory theo impact × likelihood: business critical, data loss, auth/security, compatibility, concurrency, dependency, migration, performance.
3. Map mỗi risk/criterion sang tầng test thấp nhất đủ bằng chứng: static, unit, component/integration, contract, E2E, exploratory hoặc non-functional.
4. Chốt environment/matrix: OS/runtime/browser/device/database/provider/version; chỉ chọn tổ hợp có rủi ro thực.
5. Chốt test data: synthetic/anonymized, boundary/invalid, tenant/role; cleanup và không dùng Zone C.
6. Định nghĩa entry condition, commands, expected artifacts, pass/fail/inconclusive và exit gate.
7. Ghi phần manual/exploratory không tự động hóa được, owner và lý do.
8. Duy trì trace table `criterion -> test -> evidence`; triage failure thành patch/pre-existing/environment/missing-dependency/infra-unavailable.

Ví dụ ngắn:

```text
Risk: installer bỏ sót skill mới.
Unit: manifest path/hash.
Integration: install vào temp target rồi verify 7 agents + 50 skills.
Runtime: OpenCode debug agents/skills.
Gate: static + Windows/Linux integration PASS; runtime thiếu CLI => INCONCLUSIVE.
```

## Chống chỉ định / giới hạn

- Không nhân matrix và E2E theo mọi tổ hợp nếu không có risk justification.
- Không gọi suite là pass khi skipped/unchecked criteria chưa được báo.
- Không dùng production secrets hoặc dữ liệu thật chưa được phê duyệt làm fixture.
