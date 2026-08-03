---
name: system-design
description: Produce an evidence-linked system design covering boundaries, data flows, quality attributes, failures, and operations. Apply when bx-plan converts approved requirements into an implementation-ready architecture.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-plan
  sources: BMAD-METHOD architecture workflow; C4 model official documentation; GitHub Spec Kit plan workflow
---

# System design

## Khi nào dùng

Dùng cho thay đổi xuyên subsystem, có boundary/API/data mới, hoặc có trade-off đáng kể về bảo mật, hiệu năng, độ tin cậy. Task cục bộ có thể chỉ cần design note ngắn.

## Nội dung

1. Liên kết design về goals, `REQ-*`, constraints và quality attributes đã chốt.
2. Chụp hiện trạng bằng evidence từ code/config; tách rõ `current` và `proposed`.
3. Mô tả kiến trúc tối thiểu:
   - context: actor/hệ thống ngoài và trust boundary;
   - container/deployable unit, responsibility và owner;
   - interface/protocol và luồng dữ liệu chính;
   - nơi lưu dữ liệu, consistency và lifecycle;
   - failure modes, timeout/retry/idempotency/backpressure khi liên quan;
   - authn/authz, secret và data zone;
   - observability, rollout, rollback và migration.
4. Dùng C4 context/container làm mặc định; chỉ thêm component/dynamic/deployment diagram khi giúp ra quyết định. Gắn nhãn quan hệ bằng hướng, mục đích và protocol.
5. Ghi alternatives và trade-offs; chuyển quyết định có ảnh hưởng dài hạn thành ADR.
6. Kết thúc bằng work breakdown, dependency, test strategy và readiness checklist.

Ví dụ ngắn:

```text
Context: OpenCode -> Bifrost (company boundary) -> model provider.
Contract: manifest v2 là source of truth; installer chỉ copy path đã khai báo.
Failure: model unset => doctor WARN, agent contract vẫn test độc lập được.
Rollback: khôi phục backup config và managed files.
```

## Chống chỉ định / giới hạn

- Không vẽ component/code diagram chỉ để đủ bộ C4.
- Không chọn công nghệ từ sở thích; ràng buộc mỗi lựa chọn với requirement hoặc trade-off.
- Không gọi design là implementation-ready nếu contract, migration, security boundary hoặc rollback còn mơ hồ.
