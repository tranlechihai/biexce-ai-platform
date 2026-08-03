---
name: database-migration
description: Plan and implement a backward-compatible database migration with lock, backfill, verification, rollout, and rollback controls. Apply when bx-code or bx-fix changes persistent schema or production data.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-code, bx-fix, bx-test, bx-review
  sources: PostgreSQL current ALTER TABLE, constraints, indexes, and transaction documentation; BMAD-METHOD implementation readiness
---

# Database migration

## Khi nào dùng

Dùng cho schema, constraint, index, ownership hoặc data transformation. Với production/large table, xem migration là rollout riêng có evidence, không chỉ là file SQL.

## Nội dung

1. Thu thập engine/version, table size, traffic, replicas, existing migrations và deployment order.
2. Phân tích lock, rewrite, disk, transaction duration và compatibility code cũ/code mới.
3. Ưu tiên expand–migrate–contract:
   - **Expand:** thêm cấu trúc tương thích, nullable/default an toàn.
   - **Migrate:** deploy dual-read/write nếu cần, backfill theo batch có resume.
   - **Verify:** count/checksum/invariant và quan sát error/latency.
   - **Contract:** chỉ xóa/siết ràng buộc sau khi consumer cũ không còn.
4. Đặt constraint/index theo khả năng online của engine/version; kiểm tra query plan và dung lượng sau thay đổi.
5. Migration phải có precondition, idempotency/re-run policy, progress signal và failure behavior rõ.
6. Thử trên dữ liệu đại diện; lưu command, duration, lock/evidence và rollback/recovery rehearsal.

Ví dụ ngắn:

```text
1. Add owner_id nullable + index.
2. Deploy writer, backfill batches có checkpoint.
3. Verify zero null + FK violations.
4. Enforce NOT NULL/FK theo phương án lock đã đo.
5. Remove compatibility path ở release sau.
```

## Chống chỉ định / giới hạn

- Không `DROP`, rename hoặc đổi type destructive trong cùng nhịp deploy khi code cũ còn chạy.
- Không hứa zero-downtime nếu chưa đo lock/rewrite trên đúng engine/version và dữ liệu đại diện.
- Không coi down migration là rollback duy nhất; data loss thường cần backup/restore hoặc forward fix.
