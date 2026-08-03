---
name: readme
description: Create a concise project README that lets a new contributor understand, install, run, test, and troubleshoot the supported path. Apply when README content changes.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-code, bx-review
  sources: Diataxis documentation framework; GitHub documentation on repository README files; CommonMark specification
---

# README

## Khi nào dùng

Dùng khi tạo/cập nhật README dự án hoặc package. Chỉ ghi command, version và capability đã có evidence trong repo; link tài liệu sâu thay vì nhân bản.

## Nội dung

1. Mở đầu bằng mục đích, người dùng và trạng thái thực tế trong vài câu.
2. Liệt kê prerequisite/version hỗ trợ và platform differences có ảnh hưởng.
3. Quick start là happy path ngắn có thể copy: install, config example, run, expected result.
4. Nêu cấu trúc/module chính chỉ đủ định hướng; chi tiết architecture link sang tài liệu chuyên biệt.
5. Có command test/lint/build chuẩn và ý nghĩa kết quả; không bịa command phổ biến.
6. Config chỉ dùng placeholder hoặc `.example`; chỉ rõ nơi secret phải được cung cấp, không đưa giá trị thật.
7. Troubleshooting gồm lỗi có khả năng gặp, dấu hiệu, check an toàn và link chi tiết.
8. Giữ heading/link/code block nhất quán, relative link hợp lệ và cập nhật README cùng behavior thay đổi.

Ví dụ: Quick start kết thúc bằng endpoint/output hoặc màn hình kỳ vọng, không chỉ nói “run thành công”.

## Chống chỉ định / giới hạn

- Không biến README thành changelog, API reference hoặc tài liệu vận hành đầy đủ.
- Không tuyên bố support/deploy/security chưa được xác nhận.
- Không xóa hướng dẫn platform hiện hữu chỉ để rút gọn nếu người dùng vẫn cần.
