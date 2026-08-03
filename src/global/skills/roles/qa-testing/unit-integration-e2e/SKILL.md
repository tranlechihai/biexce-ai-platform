---
name: unit-integration-e2e
description: Select and design unit, integration, contract, and end-to-end tests by the boundary each test must prove. Apply when bx-test or an implementer decides where a behavior should be verified.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-test, bx-code, bx-fix, bx-review
  sources: Martin Fowler practical test pyramid; Cucumber Gherkin reference; BIEXCE evidence format
---

# Unit, integration và E2E

## Khi nào dùng

Dùng khi thiết kế test mới, sửa test quá chậm/flaky hoặc phát hiện cùng behavior bị lặp ở nhiều tầng.

## Nội dung

- **Unit:** chứng minh rule/branch trong một boundary nhỏ; nhanh, deterministic, thay external collaborator bằng test double khi cần.
- **Integration/component:** chứng minh wiring và semantics thật với database, filesystem, network adapter, process hoặc framework.
- **Contract:** chứng minh producer/consumer đồng ý schema và behavior tại interface.
- **E2E:** chứng minh ít luồng quan trọng qua hệ thống giống thực tế; giữ số lượng nhỏ vì setup/chẩn đoán tốn kém.

Quy trình:

1. Bắt đầu từ risk/acceptance, không bắt đầu từ framework test.
2. Chọn tầng thấp nhất có thể quan sát đúng failure mode.
3. Chỉ thêm tầng cao khi nó chứng minh wiring/boundary mà tầng dưới không thể.
4. Nếu E2E tìm ra bug mà test thấp hơn không thấy, thêm regression ở tầng thấp nhất phù hợp.
5. Cô lập clock/random/external state; test parallel không dùng chung identity/path/database state ngoài kiểm soát.
6. Tên test mô tả condition + observable outcome; output failure phải chỉ ra giá trị expected/actual hữu ích.

Ví dụ ngắn:

```text
Rule parse manifest -> unit.
Copy + rollback filesystem -> integration.
OpenCode discover installed agent -> runtime E2E.
Không lặp toàn bộ hash edge cases trong runtime E2E.
```

## Chống chỉ định / giới hạn

- Không mock database rồi gọi đó là integration test.
- Không test private call order nếu contract là output/side effect công khai.
- Không dùng sleep cố định để đồng bộ async; chờ condition có timeout và diagnostics.
