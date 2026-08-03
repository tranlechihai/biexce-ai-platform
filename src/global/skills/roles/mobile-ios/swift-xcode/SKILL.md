---
name: swift-xcode
description: Implement clear Swift and Xcode changes with lifecycle-safe concurrency, stable target configuration, and platform-consistent APIs. Apply on iOS source or project tasks.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-code, bx-fix, bx-review
  sources: Swift API Design Guidelines; Apple Swift concurrency documentation; Apple Xcode project and build settings documentation
---

# Swift and Xcode

## Khi nào dùng

Dùng cho Swift, SwiftUI/UIKit, package, target hoặc Xcode configuration. Đọc deployment target, schemes, package versions và architecture hiện có trước khi sửa.

## Nội dung

1. API rõ tại điểm gọi, tên theo Swift idiom, value semantics và immutability mặc định.
2. Tách view khỏi domain/data work; UI state có owner rõ và không phụ thuộc vòng đời view ngắn hơn dữ liệu.
3. Dùng structured concurrency; xác định actor isolation, cancellation và main-thread UI update, tránh detached task tùy tiện.
4. Xử lý optional/error tường minh; không force unwrap trừ invariant nội bộ đã chứng minh và có lý do.
5. Dùng dependency injection theo convention hiện tại; side effect/time/network/storage có boundary testable.
6. Sửa `.xcodeproj`, scheme, entitlement, signing hoặc build setting tối thiểu; không ghi team ID/profile/secret cá nhân.
7. Tôn trọng deployment target và availability check; kiểm Dynamic Type, dark mode, localization và lifecycle khi liên quan.
8. Build/test đúng scheme và destination đã tài liệu hóa; phân biệt simulator với kiểm thiết bị thật.

Ví dụ: `@MainActor` view model giữ UI state, gọi service protocol qua `Task`, xử lý cancellation và map lỗi thành state người dùng.

## Chống chỉ định / giới hạn

- Không nâng Swift tools/Xcode/deployment target hoặc package hàng loạt ngoài scope.
- Không chỉnh signing tự động bằng credential của agent.
- Không trộn SwiftUI/UIKit architecture mới chỉ để refactor khi behavior hiện tại không yêu cầu.
