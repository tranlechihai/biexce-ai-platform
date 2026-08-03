---
name: secure-coding
description: Apply secure-by-default input, authorization, secret, dependency, logging, and failure controls during implementation. Use on every change that crosses a trust boundary.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-code, bx-fix, bx-review
  sources: OWASP Developer Guide and Cheat Sheet Series; NIST Secure Software Development Framework SP 800-218; CWE Top 25
---

# Secure coding

## Khi nào dùng

Dùng cho input, auth, file, database, network, process, serialization, dependency hoặc dữ liệu nhạy cảm; với code thường, dùng như baseline ngắn.

## Nội dung

1. Vẽ trust boundary và assets; validate type, length, range, encoding và allowlist ở boundary tin cậy.
2. Dùng parameterized query/API an toàn; không nối input vào SQL, shell, path, template hoặc interpreter.
3. Authentication không thay authorization; kiểm quyền object/action tại server với default deny và tenant boundary.
4. Secret chỉ từ secret store/runtime config, không hard-code/log; token/session có lifetime, revocation và secure storage phù hợp.
5. Encode output theo context; upload/path/URL có canonicalization, size/type limit và SSRF/path traversal guard khi liên quan.
6. Error cho user tối thiểu, log có correlation và audit event nhưng redact secret/PII.
7. Dependency mới cần nguồn, version, license/risk và lockfile; không vô hiệu security control để tương thích.
8. Thêm negative tests cho invalid, unauthorized, boundary và abuse path; báo rủi ro chưa kiểm thay vì tuyên bố an toàn tuyệt đối.

Ví dụ: endpoint đọc resource validate UUID, query tham số hóa, kiểm tenant ownership, trả 404/403 theo policy và không log token.

## Chống chỉ định / giới hạn

- Không tự thiết kế crypto, auth protocol hoặc secret store.
- Không sửa security policy/permission để làm test pass.
- Không thực hiện pentest chủ động ngoài target và quyền đã được phê duyệt.
