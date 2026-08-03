---
name: owasp-review
description: Review a scoped diff against concrete web, API, mobile, and software supply-chain abuse cases, producing located evidence and severity. Apply to security-relevant reviews.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-review, bx-test
  sources: OWASP Top 10 2021 and API Security Top 10 2023; OWASP ASVS 5.0; NIST Secure Software Development Framework SP 800-218
---

# OWASP review

## Khi nào dùng

Dùng khi diff chạm auth, data, API, upload, URL/file/process, dependency, logging hoặc client storage. Review theo scope và evidence, không biến thành pentest toàn hệ thống.

## Nội dung

1. Xác định entry point, trust boundary, asset, actor và operation mới/thay đổi.
2. Kiểm broken access control: object-level, function-level, tenant, role, ownership và default deny.
3. Kiểm injection/unsafe consumption: SQL, shell, path, template, SSRF, deserialization, XSS và output context.
4. Kiểm auth/session/token: lifecycle, replay, brute force, secure storage, logout/revocation và client trust.
5. Kiểm data/crypto/logging: minimization, encryption đúng lớp, secret/PII exposure, error detail và audit trail.
6. Kiểm configuration/dependency/supply chain: insecure default, debug, mutable artifact, vulnerable package và excessive permission.
7. Đối chiếu test negative/abuse case; thiếu test cho boundary thay đổi là finding khi có thể gây regression.
8. Finding gồm severity, `file:line`, evidence, exploit/impact, fix direction; verdict theo `review-verdict`.

Ví dụ: route `/users/{id}` chỉ kiểm login nhưng không kiểm ownership là finding access-control, dù UI không hiển thị link của user khác.

## Chống chỉ định / giới hạn

- Không chạy scanner/pentest lên external hoặc production target chưa được cho phép.
- Không gắn finding chỉ vì “OWASP nói vậy” nếu diff không có evidence cụ thể.
- Không sửa code; bx-review chỉ trả finding và verdict.
