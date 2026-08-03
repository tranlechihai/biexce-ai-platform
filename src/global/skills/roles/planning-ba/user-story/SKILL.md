---
name: user-story
description: Turn requirements into independently valuable, testable delivery slices with explicit dependencies. Apply when bx-plan decomposes a PRD or feature into stories suitable for implementation planning.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-plan
  sources: Agile Alliance user stories and INVEST; BMAD-METHOD story workflow; GitHub Spec Kit task model
---

# User story

## Khi nào dùng

Dùng sau khi outcome và scope đã rõ, trước task kỹ thuật. Story phù hợp cho hành vi tạo giá trị cho actor; việc thuần hạ tầng có thể dùng enabler/task nhưng vẫn phải nêu consumer và kết quả kiểm chứng.

## Nội dung

1. Cấp ID ổn định `US-*`; liên kết về `REQ-*` nguồn.
2. Viết một câu ngắn: `Là <actor>, tôi muốn <capability>, để <value>.`
3. Bổ sung context tối thiểu, acceptance criteria, out-of-scope, dependencies và evidence mong đợi.
4. Kiểm tra INVEST:
   - **Independent:** phụ thuộc được tách hoặc khai báo rõ.
   - **Negotiable:** mô tả outcome, không đóng đinh cách cài đặt không cần thiết.
   - **Valuable:** có người nhận giá trị cụ thể.
   - **Estimable:** đủ context và câu hỏi lớn đã được làm rõ.
   - **Small:** hoàn tất trong một nhịp delivery hợp lý của đội.
   - **Testable:** có tiêu chí quan sát được.
5. Tách story theo lát cắt dọc: một luồng nhỏ đi qua các lớp cần thiết. Ưu tiên tách theo workflow step, business rule, data variation, happy/error path hoặc quyền truy cập.
6. Ghi dependency bằng ID (`depends_on: US-...`) và cho phép thực hiện song song khi không có quan hệ thực.

Ví dụ ngắn:

```text
US-014 (REQ-03)
Là developer, tôi muốn gọi riêng bx-test để nhận test plan,
để kiểm chứng role trước khi bật autopilot.
Out: chạy orchestration nhiều agent.
Evidence: transcript discovery + verdict của bx-test.
```

## Chống chỉ định / giới hạn

- Không tạo story kiểu “làm backend/frontend/database” nếu từng story riêng lẻ không tạo ra hành vi kiểm chứng được.
- Không dùng story để che blocker; ghi câu hỏi, owner và điều kiện unblock rõ ràng.
- Không chia nhỏ chỉ để đạt kích thước tùy ý; ưu tiên lát cắt có giá trị và rollback được.
