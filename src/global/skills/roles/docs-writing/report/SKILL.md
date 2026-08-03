---
name: report
description: Produce concise evidence-backed task, integration, and final reports that separate outcomes, verification, gaps, and residual risk. Apply at handoff or Autopilot stages B4-B5.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-director, bx-test, bx-review
  sources: BIEXCE evidence-format and delivery contracts; Diataxis how-to and reference guidance; NIST SSDF verification records
---

# Delivery report

## Khi nào dùng

Dùng cho task handoff, integration report và final report. Report tổng hợp artifact/evidence đã có; không thay test hay review còn thiếu.

## Nội dung

1. Outcome trước: mục tiêu đạt/chưa đạt, phạm vi và verdict bằng một đoạn ngắn.
2. Bảng task/criterion có owner, status và evidence pointer; không dùng “done” nếu thiếu điều kiện contract.
3. Liệt kê file/subsystem thay đổi tách khỏi read-only input; mô tả tác động, không dump diff.
4. Verification ghi exact command/check, environment, exit/result và artifact; skipped check có lý do.
5. Failure/blocker phân loại code, pre-existing, environment, dependency hoặc infra; có bước tái hiện tối thiểu.
6. Ghi decision/waiver và người phê duyệt khi gate bị nới; không hợp thức hóa waiver ngầm.
7. Known gaps và residual risk gắn với phần chưa kiểm; dùng ngôn ngữ giới hạn theo evidence.
8. Next action có owner và điều kiện bắt đầu; final report link plan, task, test và review artifact.

Ví dụ: `Local inference: INCONCLUSIVE — VPN unavailable; rerun command X on office network. Control-plane state chain: PASS.`

## Chống chỉ định / giới hạn

- Không gọi “PASS hoàn toàn” khi có criterion chưa chạy.
- Không chôn blocker trong phần cuối hoặc thay evidence bằng mô tả tự tin.
- Không đưa secret/source nhạy cảm vào report; dùng pointer/redaction theo data policy.
