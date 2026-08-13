---
name: systematic-debugging
description: Điều tra lỗi theo evidence và root cause trước khi sửa, giới hạn giả thuyết, tránh fix mò, sleep cố định và lặp lại cùng một patch không có thông tin mới.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-director, bx-code, bx-fix, bx-test, bx-review
  sources: obra/superpowers systematic-debugging; BIEXCE evidence-format and runtime recovery policy
---

# Systematic Debugging

## Khi nào dùng

Dùng cho test fail, hành vi bất thường, regression, flaky, timeout, process/session
treo hoặc lỗi chỉ xuất hiện ở một môi trường. `bx-director` chỉ phân loại và điều
phối; việc sửa source thuộc `bx-fix` hoặc `bx-code` theo task contract.

## Quy trình bắt buộc

1. **Tái hiện:** ghi exact command, exit code, input, environment và output tối thiểu.
2. **Phân loại:** `patch`, `pre-existing`, `environment`, `missing-dependency`,
   `infra-unavailable` hoặc `runtime-control`.
3. **Khoanh vùng:** lần ngược từ symptom qua boundary gần nhất; kiểm tra dữ liệu tại
   từng boundary thay vì đoán component lỗi.
4. **So sánh:** tìm một luồng tương tự đang hoạt động và liệt kê khác biệt có thể đo.
5. **Một giả thuyết:** nêu “nguyên nhân X vì evidence Y”; chạy kiểm tra nhỏ nhất có
   thể bác bỏ giả thuyết.
6. **Patch tối thiểu:** sửa đúng root cause, thêm/giữ regression test, chạy focused
   test rồi regression theo blast radius.
7. **Báo cáo:** evidence mới, nguyên nhân, diff, phần chưa kiểm và verdict.

Với lỗi async/process, chờ theo điều kiện quan sát được (ready signal, port, state,
process exit) có timeout rõ ràng; không dùng sleep cố định để che race condition.

## Fix cap và recovery

- Chỉ source defect đã xác nhận mới tính một fix round.
- Timeout, stale lease, transport lỗi hoặc child-session abort là runtime recovery;
  runtime phải tự release/retry theo policy, không tiêu hao source fix cap.
- Mỗi vòng phải có evidence hoặc giả thuyết mới. Sau ba patch source không giải quyết
  được lỗi, dừng lặp và review lại assumption/contract/architecture.
- Không sửa state/lock bằng tay nếu runtime có recovery command chính thức.

## Giới hạn

- Không “thử vài thay đổi cùng lúc”.
- Không sửa test để hợp implementation khi requirement chưa đổi.
- Không tuyên bố root cause nếu chỉ có correlation.
- Không khởi chạy server/process vô hạn; mọi process test phải có timeout và cleanup.
