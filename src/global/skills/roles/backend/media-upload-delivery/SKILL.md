---
name: media-upload-delivery
description: Design and implement a secure mobile media upload, processing, storage, and delivery pipeline. Apply when a backend task accepts avatars, images, audio, video, attachments, or generated thumbnails.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-plan, bx-code, bx-fix, bx-test, bx-review
  sources: OWASP File Upload Cheat Sheet; Amazon S3 presigned URL and multipart upload documentation; OWASP API4 Unrestricted Resource Consumption 2023
---

# Media upload and delivery

## Khi nào dùng

Dùng cho avatar, ảnh bài viết, audio, video, attachment, thumbnail hoặc file do
user gửi lên. Chốt storage/provider theo repo; skill này không tự chọn cloud.

## Nội dung

1. Định nghĩa allow-list theo nghiệp vụ: loại file, kích thước, pixel/duration,
   số lượng, quota và trạng thái initiated -> uploaded -> processing -> ready |
   rejected | failed.
2. Dùng object key do server sinh. Nếu upload trực tiếp, signed request phải sống
   ngắn, giới hạn đúng key/method/size/checksum và không cấp quyền list/overwrite
   ngoài object đó.
3. Không tin extension hoặc Content-Type. Kiểm magic/signature và decode bằng
   thư viện an toàn; re-encode khi phù hợp, strip metadata nhạy cảm và quarantine
   trước scan/transcode.
4. Không public object trước trạng thái ready. Tách quyền upload, xem, xóa;
   private media dùng authenticated/signed delivery và kiểm tra visibility hiện
   tại, kể cả sau block hoặc đổi privacy.
5. Worker processing phải idempotent, có timeout/retry giới hạn, input/output key
   riêng và không ghi đè source. Lưu lỗi có redaction; cleanup upload dở, orphan,
   multipart và derivative khi account/content bị xóa.
6. Bảo vệ resource: rate/quota, concurrency, decompression bomb, image dimension,
   duration và storage egress. Đặt cache/CDN header theo privacy và versioned key.
7. Test spoofed MIME, oversized/damaged file, unauthorized object, expired signed
   URL, duplicate callback, worker retry, delete propagation và cleanup.

Ví dụ ngắn:

    POST /media/init -> upload_id + signed PUT.
    POST /media/{id}/complete -> verify checksum -> quarantine -> process -> ready.

## Chống chỉ định / giới hạn

- Không lưu raw filename làm filesystem path hoặc public object key.
- Không cho client tự đánh dấu ready hay tự gửi URL storage tùy ý.
- Không chạy antivirus/transcode nặng trong request web đồng bộ nếu có thể làm
  cạn worker hoặc timeout toàn API.
