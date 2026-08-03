---
name: testing-frontend
description: Verify frontend behavior through user-observable outcomes using a risk-based mix of component, integration, accessibility, and end-to-end tests. Apply when UI behavior changes.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-code, bx-test, bx-review
  sources: Testing Library guiding principles and query priority; Playwright official best practices; W3C WCAG 2.2
---

# Frontend testing

## Khi nào dùng

Dùng khi thêm/sửa hành vi UI, data fetching, routing, form hoặc accessibility. Chọn tầng test hẹp nhất vẫn chứng minh được boundary rủi ro.

## Nội dung

1. Unit test logic thuần; component/integration test interaction và rendering; E2E giữ cho vài user journey quan trọng.
2. Query theo role, label, text và accessible name; tránh class, DOM path hoặc test-id nếu có semantic phù hợp.
3. Mô phỏng hành vi user thực: click, type, tab; assert kết quả nhìn thấy được, URL hoặc request contract.
4. Bao phủ loading, empty, error, retry, validation, unauthorized và response sai thứ tự khi có async.
5. Fake tại boundary network/time/storage; không mock implementation nội bộ khiến integration hỏng vẫn pass.
6. Test độc lập và deterministic: dữ liệu riêng, cleanup rõ, không phụ thuộc thứ tự hoặc sleep tùy ý.
7. Accessibility check gồm semantic và keyboard; automation không thay screen-reader review cho luồng chính.
8. Khi sửa bug, thêm regression tái hiện đúng failure rồi xác nhận pass sau sửa.

Ví dụ: test form tìm field theo label, nhập dữ liệu, submit, kiểm trạng thái chờ rồi thông báo thành công; fake ở transport boundary.

## Chống chỉ định / giới hạn

- Không snapshot toàn trang làm bằng chứng duy nhất cho behavior.
- Không tăng timeout để che flaky race.
- Không lặp cùng hành vi ở mọi tầng nếu không chứng minh thêm boundary nào.
