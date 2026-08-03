---
name: ci-config
description: Author least-privilege, deterministic CI pipelines with fast feedback, protected secrets, and reproducible evidence. Apply when a task adds or edits CI configuration.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-code, bx-review
  sources: GitHub Actions secure-use documentation; GitLab CI/CD pipeline security documentation; NIST Secure Software Development Framework
---

# CI configuration

## Khi nào dùng

Dùng khi viết/review pipeline CI. Xác định nền tảng, protected branch, runner, required checks và command chuẩn từ repo; không đoán hệ thống deploy.

## Nội dung

1. Pipeline theo stage rõ: validate/lint, unit, integration/build; job độc lập và fail-fast khi hợp lý.
2. Pin action/image/tool version; dùng lock/cache key từ dependency file, không cache secret hoặc output không tin cậy.
3. Permission token tối thiểu; pull request không tin cậy không được nhận production secret hay runner đặc quyền.
4. Truyền untrusted context qua argument/env an toàn, tránh ghép trực tiếp vào shell gây injection.
5. Secret lấy từ secret store, redact log, ưu tiên credential ngắn hạn/OIDC và environment approval khi có.
6. Artifact có tên, retention và nội dung tối thiểu; log command, exit code, test report đủ tái hiện nhưng không lộ dữ liệu.
7. Matrix chỉ gồm platform/version được support; giới hạn concurrency và timeout để tránh job treo/lãng phí.
8. Validate syntax và chạy local/narrow check nếu có; thay đổi deploy luôn cần owner/phê duyệt riêng.

Ví dụ: PR chạy lint+unit với read-only token; merge protected mới build artifact; release job cần environment reviewer và credential ngắn hạn.

## Chống chỉ định / giới hạn

- Không bật auto-deploy, thay branch protection hoặc cấp secret/runner permission ngoài task.
- Không bỏ/soft-fail check để pipeline xanh.
- Không dùng mutable latest tag cho action/image quan trọng nếu có thể pin.
