---
name: adr
description: Record an architecturally significant decision with context, options, consequences, and lifecycle. Apply when bx-plan must preserve why a durable technical choice was made or superseded.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-plan, bx-review
  sources: AWS Prescriptive Guidance architectural decision records; BMAD-METHOD architecture workflow
---

# ADR

## Khi nào dùng

Dùng khi quyết định ảnh hưởng structure, interface, data, security, operations hoặc nhiều task tương lai. Không cần ADR cho refactor cục bộ dễ đảo ngược và không tạo convention mới.

## Nội dung

1. Cấp ID bất biến `ADR-NNN` và tiêu đề là quyết định, không phải chủ đề chung.
2. Ghi `status`: proposed, accepted, rejected, deprecated hoặc superseded; kèm ngày và decision owner.
3. Mô tả context: forces, constraints, assumptions, evidence và decision drivers.
4. Liệt kê lựa chọn thực sự đã cân nhắc, kể cả giữ nguyên hiện trạng.
5. Ghi decision và phạm vi áp dụng bằng câu chủ động.
6. Ghi consequences hai chiều: lợi ích, chi phí, rủi ro, migration, operational impact và điều kiện xem xét lại.
7. Liên kết requirement/design/task liên quan. Khi thay đổi quyết định accepted, tạo ADR mới và đánh dấu ADR cũ `superseded by` thay vì sửa lịch sử.

Ví dụ ngắn:

```text
ADR-004: Manifest v2 là source of truth cho managed files
Status: accepted
Decision: installer/verifier/package đọc agents và skills từ manifest.
Consequence: thêm skill phải regenerate hash; bỏ được danh sách hardcode.
```

## Chống chỉ định / giới hạn

- Không ghi ADR sau quyết định mà bỏ context/alternatives chỉ để hợp thức hóa.
- Không nhét chi tiết implementation thay đổi thường xuyên vào ADR.
- Không sửa nội dung quyết định đã accepted; dùng ADR kế nhiệm để giữ audit trail.
