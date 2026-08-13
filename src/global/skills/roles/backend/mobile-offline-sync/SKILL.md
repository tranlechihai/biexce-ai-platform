---
name: mobile-offline-sync
description: Design and implement mobile API synchronization for unreliable networks with delta cursors, idempotent writes, conflict rules, and tombstones. Apply when a mobile backend supports offline reads, queued mutations, multi-device state, or incremental sync.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-plan, bx-code, bx-fix, bx-test, bx-review
  sources: Android Developers offline-first architecture; RFC 9110 HTTP Semantics; PostgreSQL current transaction isolation documentation
---

# Mobile offline sync

## Khi nào dùng

Dùng khi mobile app phải hoạt động qua mạng chậm/mất kết nối, retry mutation,
đồng bộ nhiều thiết bị hoặc tải delta. Chốt online-only, queued hay lazy write
theo từng hành vi; không mặc định mọi write đều offline được.

## Nội dung

1. Xác định server là authority cho entity/version nào và dữ liệu nào client có
   thể cache. Ghi rõ freshness, retention và trường hợp bắt buộc online.
2. Thiết kế delta endpoint với cursor opaque, scope theo user/tenant/query và
   ordering ổn định. Cursor hết hạn hoặc scope đổi phải trả tín hiệu reset để
   client lấy snapshot, không âm thầm bỏ dữ liệu.
3. Mutation retryable dùng Idempotency-Key hoặc client_mutation_id; cùng key +
   cùng payload trả cùng kết quả, key trùng payload khác bị conflict. Không dùng
   device timestamp làm authority.
4. Dùng server version/ETag hoặc revision để optimistic concurrency. Chọn conflict
   rule theo entity: set-like/reaction có thể merge idempotent; edit post/profile
   cần expected version; counter do server tính; nghiệp vụ nhạy cảm có thể online-only.
5. Truyền delete, block, revoke và privacy change bằng tombstone/version đủ lâu
   cho client offline; định nghĩa purge sau retention và behavior của client quá cũ.
6. Giới hạn page/batch/payload, nén khi phù hợp và dùng backoff + jitter. Sync phải
   resume sau partial failure, không commit cursor trước dữ liệu tương ứng.
7. Test duplicate/reordered request, timeout sau server commit, hai thiết bị sửa
   cùng entity, stale cursor, deleted item, block/privacy, clock lệch và upgrade
   schema/app version.

Ví dụ ngắn:

    POST /posts/{id}/like {client_mutation_id}; retry không tăng count hai lần.
    GET /sync?cursor=opaque trả changes + tombstones + next_cursor.

## Chống chỉ định / giới hạn

- Không dùng last-write-wins chung cho mọi entity nếu có thể mất dữ liệu/nghiệp vụ.
- Không coi push notification là dữ liệu đồng bộ; nó chỉ báo client nên fetch.
- Không giữ tombstone, idempotency record hoặc change log vô hạn; phải có retention
  dựa trên thời gian offline được hỗ trợ.
