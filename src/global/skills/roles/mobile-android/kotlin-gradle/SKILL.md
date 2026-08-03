---
name: kotlin-gradle
description: Implement maintainable Android features with Kotlin, lifecycle-safe state, explicit module boundaries, and reproducible Gradle configuration. Apply on Android source or build tasks.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-code, bx-fix, bx-review
  sources: Android Developers app architecture guide; Kotlin official coding conventions and coroutines guide; Gradle official build best practices
---

# Kotlin and Gradle

## Khi nào dùng

Dùng cho Android/Kotlin/Gradle. Đọc version catalog, module graph, min/target SDK, UI toolkit và architecture hiện có trước khi sửa.

## Nội dung

1. Tách UI và data boundary; UI lấy state từ state holder/ViewModel, không giữ domain data trong Activity/Fragment.
2. Duy trì unidirectional data flow và một source of truth; model per layer khi mapping giúp cô lập API/storage/UI.
3. Coroutine có owner và lifecycle rõ; structured concurrency, dispatcher phù hợp, không block main thread.
4. API Kotlin rõ tại call site, nullability chính xác, immutable mặc định và tuân convention dự án.
5. Dependency injection theo cơ chế đang có; không tự tạo service locator/singleton mới.
6. Gradle thay đổi nhỏ và reproducible: pin version, dùng catalog/plugin convention sẵn có, không thêm repository tùy tiện.
7. Giữ backward compatibility với min SDK và xử lý configuration/process recreation, offline/intermittent network khi liên quan.
8. Chạy task Gradle đã được repo tài liệu hóa và test trên device/emulator cho phần phụ thuộc Android framework.

Ví dụ: screen nhận `StateFlow<UiState>` từ ViewModel; repository là source of truth; `viewModelScope` gọi use case main-safe.

## Chống chỉ định / giới hạn

- Không nâng AGP, Kotlin, Gradle hoặc SDK nếu task không yêu cầu và chưa kiểm ma trận tương thích.
- Không nhét business logic vào composable/Activity.
- Không thêm module hoặc abstraction chỉ để theo mẫu chung khi codebase nhỏ và ranh giới hiện tại đủ rõ.
