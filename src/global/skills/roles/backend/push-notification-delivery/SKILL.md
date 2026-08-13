---
name: push-notification-delivery
description: Design and implement reliable privacy-aware mobile push notification delivery. Apply when a backend task registers device tokens, sends FCM or APNs messages, handles preferences, retries, deep links, or delivery feedback.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-plan, bx-code, bx-fix, bx-test, bx-review
  sources: Firebase Cloud Messaging architecture and scale guidance; Apple UserNotifications remote notification provider documentation; RFC 8030 Generic Event Delivery Using HTTP Push
---

# Push notification delivery

## Khi nào dùng

Dùng cho device-token registration, notification/data message, badge, deep link,
preferences và delivery feedback trên Android/iOS. Push chỉ là tín hiệu; API và
database vẫn là source of truth.

## Nội dung

1. Lưu registration theo user, device/install, platform, app/environment và thời
   điểm cập nhật. Token là secret-like data: không log/prompt; hỗ trợ rotate,
   logout, account switch và xóa token invalid/unregistered.
2. Tạo notification từ domain event qua transactional outbox để không mất event
   hoặc gửi trước khi transaction chính commit. Worker gửi phải idempotent.
3. Chốt loại message, collapse/dedup key, TTL, priority và deep-link allow-list.
   Payload tối thiểu, không chứa token đăng nhập, private content hoặc PII có thể
   hiện trên lock screen; client fetch chi tiết sau khi authorize.
4. Áp dụng preference, quiet hours, block/mute, relationship và content visibility
   tại thời điểm enqueue/gửi. Thay đổi privacy phải ngăn notification chưa gửi.
5. Retry transient có exponential backoff + jitter và giới hạn; permanent error
   thì không retry mù. Tôn trọng provider quota/throttle và batch theo giới hạn
   thật của SDK/API đang dùng.
6. Phân biệt accepted by provider, delivered, opened và read; không dùng accepted
   làm bằng chứng user đã nhận. Audit campaign/event ID nhưng redaction payload.
7. Tách credential/config sandbox và production. Test token rotation, duplicate
   event, invalid token, throttle, preference, blocked user, stale deep link và
   payload privacy.

Ví dụ ngắn:

    CommentCreated -> outbox(notification_id) -> worker -> FCM/APNs.
    Payload chỉ có notification_id + route; app gọi API lấy nội dung đã authorize.

## Chống chỉ định / giới hạn

- Không gửi trực tiếp tới FCM/APNs bên trong transaction hoặc request người dùng.
- Không dùng topic công khai cho nhóm có membership/visibility nhạy cảm nếu không
  có cơ chế revoke đáng tin cậy.
- Không retry vô hạn hoặc giữ token invalid chỉ để tăng số thiết bị đăng ký.
