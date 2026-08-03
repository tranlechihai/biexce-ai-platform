---
name: unity-project-rules
description: Implement Unity 6 mobile gameplay and UI changes while preserving project structure, asset integrity, assembly boundaries, and device performance. Apply on Unity source or asset tasks.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-code, bx-fix, bx-review
  sources: Unity 6 Manual on assembly definitions and prefabs; Unity Test Framework documentation; Unity Profiler target-device guidance
---

# Unity project rules

## Khi nào dùng

Dùng cho Unity C#, scene, prefab, ScriptableObject, package hoặc mobile gameplay/UI. Đọc `ProjectSettings/ProjectVersion.txt`, asmdef, folder convention và component contract hiện có trước khi sửa.

## Nội dung

1. Giữ nguyên kiến trúc dự án; dùng interface/event/service hiện có, không thêm global singleton hoặc framework mới nếu task không yêu cầu.
2. MonoBehaviour điều phối lifecycle/Unity API; domain logic thuần C# khi cần test. Không làm việc nặng trong `Update` nếu có thể event/timer/pool.
3. Tôn trọng asmdef và hướng dependency; runtime assembly không tham chiếu Editor/test assembly.
4. Prefab là nguồn dùng lại; sửa đúng prefab/variant, tránh override scene ngẫu nhiên và không sửa GUID/meta thủ công.
5. Serialize field có chủ đích, giữ backward compatibility cho asset đã tồn tại; rename field cần migration như `FormerlySerializedAs` khi phù hợp.
6. Mobile-first: tránh allocation mỗi frame, cache reference, pool object thường xuyên, kiểm input/touch/safe area và lifecycle pause/resume.
7. Scene/prefab thay đổi cần mô tả object/component/serialized property; không coi text diff là đủ bằng chứng visual/runtime.
8. Profile performance trên target device; Editor chỉ cho tín hiệu ban đầu, không phải số liệu release.

Ví dụ: tower lấy target qua service hiện có, fire theo timer, projectile dùng pool; damage logic thuần C# và prefab giữ serialized reference.

## Chống chỉ định / giới hạn

- Không sửa `Library/`, `Temp/`, `Logs/`, generated solution hoặc vendor package.
- Không tạo singleton/service locator mới hoặc refactor toàn project cho một task nhỏ.
- Không nhận scene/prefab “pass” nếu chưa import/compile và kiểm trong Unity khi task đụng asset.
