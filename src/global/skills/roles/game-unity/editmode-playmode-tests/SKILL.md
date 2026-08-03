---
name: editmode-playmode-tests
description: Choose and execute Unity Edit Mode, Play Mode, scene, and device checks that prove gameplay behavior without brittle timing. Apply when verifying Unity work.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-code, bx-test, bx-review
  sources: Unity Test Framework Edit Mode and Play Mode documentation; Unity 6 Test Framework manual; Unity Profiler target-device guidance
---

# Unity Edit Mode and Play Mode tests

## Khi nào dùng

Dùng khi Unity behavior thay đổi. Chọn Edit Mode cho logic/editor API không cần player loop; Play Mode cho lifecycle, coroutine, physics, scene/prefab và frame-dependent behavior.

## Nội dung

1. Map acceptance criterion sang tầng hẹp nhất: pure C# Edit Mode, Unity integration Play Mode, manual scene check hoặc device profile.
2. Test assembly có asmdef đúng, reference tối thiểu và tách Editor/runtime rõ.
3. Edit Mode test domain rule, serialization helper, data validation và editor tooling; không giả lập player loop bằng thủ thuật.
4. Play Mode test `Awake/Start`, coroutine, physics, pooling, UI/event và scene/prefab wiring cần runtime.
5. Điều khiển time/random/dependency; chờ condition/frame cụ thể, không dùng delay dài tùy ý gây flaky.
6. Dọn GameObject, scene, asset tạm trong teardown; test độc lập và không làm bẩn project.
7. Chạy batchmode theo command dự án và lưu XML/log/exit code; phân loại compile, test, environment và device failure.
8. Với mobile, smoke trên target device và profile CPU/GPU/memory cho thay đổi nhạy hiệu năng.

Ví dụ: damage calculation chạy Edit Mode; projectile spawn-hit-despawn qua pool chạy Play Mode; frame time kiểm riêng trên thiết bị mục tiêu.

## Chống chỉ định / giới hạn

- Không ép toàn bộ test thành Play Mode nếu logic thuần có thể kiểm nhanh hơn.
- Không sửa time scale hoặc global project setting mà không phục hồi.
- Không xem test runner xanh là bằng chứng scene/prefab visual hoặc hiệu năng thiết bị đã đạt.
