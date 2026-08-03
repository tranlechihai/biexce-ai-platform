---
name: acceptance-criteria
description: Write observable, unambiguous acceptance criteria that can drive review and tests. Apply when bx-plan defines a story or bx-review checks whether delivered behavior satisfies it.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-plan, bx-review
  sources: Cucumber Gherkin reference; Scrum.org acceptance criteria guidance; GitHub Spec Kit specification workflow
---

# Acceptance criteria

## Khi nào dùng

Dùng cho từng story/feature để xác định điều kiện chấp nhận cụ thể. Đây là tiêu chí của hạng mục; Definition of Done vẫn là chuẩn chất lượng chung cho mọi hạng mục.

## Nội dung

1. Viết từ góc nhìn hành vi quan sát được, không mô tả private method hay thứ tự gọi nội bộ.
2. Bao phủ đủ nhóm liên quan: happy path, validation/edge, lỗi và recovery, authorization, dữ liệu, tương thích; thêm hiệu năng/accessibility chỉ khi scope yêu cầu.
3. Mỗi criterion phải có:
   - precondition hoặc dữ liệu đầu vào;
   - một event/action chính;
   - kết quả cụ thể có thể assert;
   - nguồn requirement (`REQ-*`/`US-*`).
4. Dùng Given/When/Then khi nó làm scenario rõ hơn:
   - **Given:** trạng thái ban đầu, không phải thao tác kiểm thử.
   - **When:** sự kiện duy nhất đang được kiểm tra.
   - **Then:** kết quả nhìn thấy ở boundary công khai.
5. Tách scenario nếu có nhiều `When`, nhiều outcome độc lập hoặc quá nhiều nhánh `And`.
6. Đánh dấu cách lấy evidence: automated test, command output, API response, screenshot hoặc manual check có lý do.

Ví dụ ngắn:

```gherkin
Scenario: agent chưa gắn model
  Given manifest có model_binding.state là unset
  When chạy biexce doctor
  Then kết quả cảnh báo binding chưa sẵn sàng và không báo inference PASS
```

## Chống chỉ định / giới hạn

- Không dùng từ mơ hồ như “nhanh”, “đẹp”, “ổn định” nếu không có phép đo và baseline.
- Không biến acceptance criteria thành checklist implementation hoặc Definition of Done chung.
- Không tự suy diễn tiêu chí kinh doanh; đưa mục chưa rõ vào question/blocker.
