---
name: estimate
description: Size delivery effort as a transparent range with assumptions, uncertainty, and dependencies. Apply when bx-plan prioritizes or sequences tasks in a Master Plan.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-plan
  sources: Scrum Guide 2020; GitHub Spec Kit task model; BIEXCE pilot calibration policy
---

# Estimate

## Khi nào dùng

Dùng sau khi task có scope, acceptance và dependency đủ rõ. Estimate phục vụ sequencing/capacity; không phải cam kết deadline và không thay thế đo thời gian thực tế.

## Nội dung

1. Tách task nếu có nhiều outcome, nhiều owner hoặc không thể kiểm chứng độc lập.
2. Chấm bốn yếu tố: phạm vi thay đổi, độ mới/kỹ thuật, dependency/môi trường, mức evidence cần tạo.
3. Gán cỡ tương đối theo baseline của chính đội:
   - `S`: đường đi quen thuộc, phạm vi hẹp, test trực tiếp, không có external blocker.
   - `M`: nhiều file/layer hoặc có migration/contract, nhưng rủi ro đã hiểu.
   - `L`: nhiều subsystem, dependency ngoài, thiết kế chưa chốt hoặc rollback phức tạp; ưu tiên tách/spike.
4. Ghi cùng estimate: assumptions, unknowns, dependencies, confidence (`high/medium/low`) và lý do.
5. Với unknown kỹ thuật lớn, tạo spike time-boxed có câu hỏi và deliverable; estimate lại sau evidence.
6. Hiệu chỉnh S/M/L bằng dữ liệu các pilot BIEXCE đã hoàn tất; không áp vận tốc của đội/project khác.

Ví dụ ngắn:

```text
A2.3 verify/installer: M, confidence medium.
Assume manifest v2 schema đã khóa; dependency: OpenCode CLI 1.18.x.
Risk: khác biệt PowerShell/Linux; evidence: hai integration suites.
```

## Chống chỉ định / giới hạn

- Không đổi S/M/L thành số giờ chính xác khi chưa có calibration.
- Không giảm estimate chỉ vì agent sinh code nhanh; review, test, rollback và môi trường vẫn là effort.
- Không estimate qua blocker chưa có owner; báo `BLOCKED` và điều kiện gỡ blocker.
