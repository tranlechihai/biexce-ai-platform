---
name: test-driven-development
description: Triển khai hành vi và sửa lỗi bằng vòng RED-GREEN-REFACTOR thực dụng khi có thể tự động kiểm chứng, ưu tiên test hành vi thật và thay đổi nhỏ.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-code, bx-fix, bx-test, bx-review
  sources: obra/superpowers test-driven-development; BIEXCE unit-integration-e2e and acceptance criteria
---

# Test-Driven Development

## Khi nào dùng

Dùng cho behavior mới, regression và bug có thể kiểm chứng tự động. Với code legacy,
viết characterization test trước khi thay đổi. Với docs/config/schema, thay test code
bằng validator, lint, parser hoặc contract check tương ứng.

Không bắt buộc TDD cho spike bị giới hạn thời gian, generated code, visual-only check
hoặc môi trường chưa thể chạy; phải ghi rõ lý do và test bù trước khi `DONE`.

## Vòng RED → GREEN → REFACTOR

1. Chọn đúng một hành vi từ acceptance criterion.
2. Viết test nhỏ kiểm tra output/cạnh tranh/error quan sát được, hạn chế mock chi tiết
   implementation.
3. Chạy test và xác nhận **RED vì đúng lý do**; lỗi syntax/setup không phải RED hợp lệ.
4. Viết implementation nhỏ nhất để test **GREEN**; không thêm behavior ngoài scope.
5. Chạy focused test, sau đó refactor mà không đổi behavior.
6. Chạy regression theo blast radius và lưu exact command/exit evidence.
7. Lặp cho criterion tiếp theo.

Bug fix phải có test tái hiện nếu feasible. Không xóa hoặc viết lại source có sẵn chỉ
để “đúng TDD”; bảo toàn user change và dùng characterization test khi cần.

## Test tốt

- Tên mô tả hành vi, chỉ kiểm một ý chính và deterministic.
- Ưu tiên public contract; chỉ mock boundary chậm/không ổn định/bên ngoài.
- Có happy path, lỗi quan trọng và boundary được acceptance yêu cầu.
- Test phải thất bại nếu behavior bị bỏ, không chỉ kiểm mock đã được gọi.

## Handoff

`bx-code`/`bx-fix` giao diff và focused evidence. `bx-test` chạy độc lập acceptance và
regression; `bx-review` kiểm tra test có chứng minh behavior hay chỉ phản chiếu code.

## Giới hạn

- Không gọi GREEN nếu chưa chạy test trong working tree hiện tại.
- Không đổi expected result để làm test pass.
- Không dùng toàn bộ suite chậm thay cho focused RED/GREEN khi có test hẹp hơn.
