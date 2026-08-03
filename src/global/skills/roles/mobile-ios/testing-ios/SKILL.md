---
name: testing-ios
description: Verify iOS logic, integration, UI journeys, and performance using Swift Testing and XCTest at the appropriate boundary. Apply when Apple-platform behavior changes.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-code, bx-test, bx-review
  sources: Apple Swift Testing documentation; Apple XCTest documentation; Apple Xcode testing guide
---

# iOS testing

## Khi nào dùng

Dùng khi thay đổi Swift/iOS behavior. Ưu tiên Swift Testing cho unit/integration mới; giữ XCTest cho UI, performance và suite hiện hữu theo hướng dẫn Apple.

## Nội dung

1. Nhiều unit test nhanh cho domain/state; ít integration test cho wiring; UI test chỉ cho critical journey.
2. Inject network, clock, persistence và scheduler; test deterministic, không phụ thuộc dịch vụ thật hoặc thời gian tường.
3. Với async, kiểm success, error, cancellation, timeout và actor/main-thread behavior; không dùng sleep cố định.
4. Dùng parameterized test cho boundary cases; mỗi test mô tả một behavior quan sát được.
5. XCTest UI tìm element qua accessibility identifier/label ổn định, không theo tọa độ.
6. Bao phủ launch/relaunch, permission denial, offline, background/foreground và restore khi feature liên quan.
7. Performance test có baseline, workload ổn định và destination ghi rõ; simulator không thay thiết bị thật.
8. Chạy subset khi phát triển và full affected test plan trước review; lưu command/scheme/destination làm evidence.

Ví dụ: unit test service mapping bằng Swift Testing; XCTest UI xác nhận luồng đăng nhập thất bại/thành công bằng accessible identifiers.

## Chống chỉ định / giới hạn

- Không migrate toàn bộ XCTest sang Swift Testing trong một feature nhỏ.
- Không mix API hai framework trong cùng test.
- Không gọi network production, dùng account thật hoặc chứa signing secret trong fixture.
