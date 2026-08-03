---
name: data-model
description: Design a data model around domain invariants, ownership, access patterns, lifecycle, and migration. Apply when bx-plan introduces or changes persistent data across a system boundary.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-plan, bx-review
  sources: PostgreSQL current documentation on constraints and indexes; OWASP ASVS; BMAD-METHOD architecture workflow
---

# Data model

## Khi nào dùng

Dùng khi thêm entity, thay schema, thay ownership/lifecycle hoặc cần chia sẻ dữ liệu giữa component. Không cần model tài liệu lớn cho thay đổi field cục bộ đã có convention rõ.

## Nội dung

1. Xác định entity/value object, vocabulary và business invariant trước bảng/collection.
2. Với mỗi field ghi: type/format, required/null, default, source, classification, retention và owner.
3. Chọn identity/key ổn định; mô hình hóa relationship và cardinality rõ ràng.
4. Đưa invariant có thể đảm bảo vào database bằng `NOT NULL`, `CHECK`, `UNIQUE`, PK/FK hoặc tương đương; giữ validation thân thiện ở application boundary.
5. Liệt kê read/write query và concurrency pattern; thiết kế index theo workload đã biết, không index mọi cột.
6. Chốt transaction boundary, consistency, delete/cascade/soft-delete, audit và recovery.
7. Đánh dấu Zone A/B/C, PII/secret và quy tắc encryption/access/logging.
8. Kèm migration/backfill/verification/rollback; nêu compatibility giữa code cũ và schema mới.

Ví dụ ngắn:

```text
Run(id, owner_id, state, created_at)
Invariant: state thuộc queued|running|done|failed.
Access: list by owner, newest first -> index(owner_id, created_at desc).
Retention: theo company policy; payload Zone B không đưa ra cloud mặc định.
```

## Chống chỉ định / giới hạn

- Không dùng application validation làm hàng rào duy nhất cho invariant quan trọng nếu datastore hỗ trợ constraint.
- Không chọn index hoặc denormalize nếu chưa có access pattern/evidence.
- Không chạy migration destructive/locking trên production khi chưa đánh giá lock, backup, rollout và rollback.
