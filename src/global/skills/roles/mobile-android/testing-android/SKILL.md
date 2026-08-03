---
name: testing-android
description: Verify Android logic, lifecycle, persistence, navigation, and device behavior with deterministic local and instrumented tests. Apply when Android behavior changes.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-code, bx-test, bx-review
  sources: Android Developers testing fundamentals and architecture recommendations; Jetpack Compose testing documentation; Gradle official test guidance
---

# Android testing

## Khi nào dùng

Dùng khi thêm/sửa Android behavior. Chọn `test/` cho JVM-local logic và `androidTest/` khi cần framework, database thật, navigation, Compose hoặc device.

## Nội dung

1. Unit test ViewModel/state holder, reducer, repository/data source và boundary/error path.
2. Ưu tiên fake có hành vi rõ hơn mock interaction dày; clock, dispatcher, network và storage phải điều khiển được.
3. Test Flow/StateFlow theo state quan sát được; kiểm initial, success, error, cancellation và stale response.
4. Instrumented test cho integration cần Android; UI test theo semantics/accessibility thay vì tọa độ hoặc tree nội bộ.
5. Bao phủ recreation, rotation, process restore, permission denial, offline và low-memory path khi feature phụ thuộc.
6. Test độc lập: dữ liệu unique, reset database/preferences, không dùng sleep cố định.
7. Tách smoke journey quan trọng khỏi test chi tiết để CI nhanh; ghi rõ device/API level đã chạy.
8. Regression cho bug phải tái hiện failure trước sửa và gắn với acceptance criterion.

Ví dụ: ViewModel test dùng fake repository và test dispatcher; instrumented test chỉ chứng minh Room wiring và navigation trên emulator.

## Chống chỉ định / giới hạn

- Không dùng Robolectric/instrumented test cho logic thuần có thể kiểm nhanh trên JVM.
- Không coi emulator duy nhất là bằng chứng hiệu năng hoặc behavior mọi thiết bị.
- Không tăng idling timeout để che công việc async chưa được quản lý.
