---
name: auth-security
description: Implement and review backend authentication, authorization, session/token, secret, and audit controls using default-deny boundaries. Apply when bx-code, bx-fix, or bx-review touches identity or protected resources.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-code, bx-fix, bx-review, bx-test
  sources: OWASP ASVS 5.0; OWASP API Security Top 10 2023; BIEXCE company security policy
---

# Auth security

## Khi nào dùng

Dùng khi thêm/sửa login, token/session, role/scope, object access, admin action, credential hoặc audit. Security boundary chưa rõ là blocker cần bx-plan/chủ dự án chốt.

## Nội dung

1. Lập ma trận `actor x action x resource x condition`; mặc định deny, cấp quyền tối thiểu.
2. Tách authentication (ai) khỏi authorization (được làm gì); kiểm tra authorization ở server trên mọi request và object.
3. Dùng thư viện/protocol đã được repo phê duyệt; không tự thiết kế crypto, password hashing hoặc token format.
4. Với session/token: xác minh issuer/audience/signature/expiry khi áp dụng; có rotation, revocation/logout, replay/CSRF protection theo transport.
5. Credential/secret chỉ lấy từ secret store/environment đã duyệt; không hardcode, log, gửi vào prompt hoặc commit.
6. Validate input trước use; encode/output theo context; dùng parameterized query và safe API cho command/path.
7. Rate/resource-limit các flow nhạy cảm; response không được tiết lộ user tồn tại, policy nội bộ hoặc material giúp tấn công.
8. Audit sự kiện bảo mật bằng actor, action, target, result, time/correlation; redaction dữ liệu nhạy cảm.
9. Test allow + deny: unauthenticated, wrong role/scope, wrong owner/tenant, expired/revoked, tamper/replay và audit.

Ví dụ ngắn:

```text
DELETE /projects/{id}
Require authenticated actor + project:delete + ownership/tenant match.
Test: owner allowed; other tenant forbidden; missing token unauthorized.
```

## Chống chỉ định / giới hạn

- Không dựa vào UI ẩn nút hoặc client claim để authorize.
- Không mở rộng quyền để “test cho chạy”; sửa fixture/policy đúng phạm vi.
- Không tuyên bố compliant với ASVS nếu chưa xác định version, level/scope và evidence kiểm chứng.
