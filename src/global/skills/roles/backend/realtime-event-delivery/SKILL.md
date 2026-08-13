---
name: realtime-event-delivery
description: Design and implement secure resumable realtime event delivery over WebSocket or SSE. Apply when a backend task adds chat, presence, live counters, notifications, subscriptions, reconnect, or streaming updates.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-plan, bx-code, bx-fix, bx-test, bx-review
  sources: RFC 6455 The WebSocket Protocol; OWASP WebSocket Security Cheat Sheet; RFC 9110 HTTP Semantics
---

# Realtime event delivery

## Khi nào dùng

Dùng khi requirement thật sự cần server push, chat, presence hoặc live update.
Nếu polling/invalidation notification đáp ứng được latency và tải, ưu tiên giải
pháp đơn giản hơn.

## Nội dung

1. Chọn WebSocket cho hai chiều, SSE cho server-to-client hoặc polling cho nhu
   cầu thưa. Ghi rõ delivery guarantee, ordering scope và fallback.
2. Authenticate handshake bằng cơ chế repo duyệt; không đặt long-lived secret
   trong URL. Revalidate expiry/revocation và authorize từng subscription,
   channel, room và message theo tenant/ownership.
3. Chuẩn hóa envelope có event_id, type, version, stream, sequence hoặc cursor và
   payload tối thiểu. Consumer phải xử lý duplicate idempotent và event version
   không biết theo policy rõ.
4. Chỉ đảm bảo ordering trong stream đã chốt. Hỗ trợ resume từ cursor hợp lệ;
   nếu có gap/expired cursor thì yêu cầu client resync snapshot qua API thay vì
   đoán state.
5. Đặt message/frame size, subscription count, connection/user/IP quota, bounded
   send queue và backpressure policy. Client chậm phải bị drop/coalesce/disconnect
   có chủ đích, không làm tăng memory vô hạn.
6. Dùng heartbeat/idle timeout, cleanup subscription khi disconnect và graceful
   shutdown. Nếu publish sau DB commit, dùng outbox/event bus idempotent.
7. Không xem realtime event là source of truth. Test unauthorized subscribe,
   token revoke, reconnect/resume, duplicate/out-of-order, slow consumer,
   malformed frame, disconnect storm và fallback resync.

Ví dụ ngắn:

    Event: {event_id, type:post.updated.v1, stream:feed:u1, sequence:42}.
    Client thấy 40 -> 42 thì gọi delta/snapshot API trước khi áp dụng tiếp.

## Chống chỉ định / giới hạn

- Không broadcast trước khi kiểm tra per-recipient visibility.
- Không đưa toàn bộ entity/PII vào event nếu ID + authorized fetch là đủ.
- Không tuyên bố exactly-once trên mạng; thiết kế at-least-once hoặc best-effort
  rõ ràng cùng idempotency/resync.
