---
name: abuse-moderation
description: Design and review abuse prevention, reporting, blocking, moderation state, and auditable enforcement for social APIs. Apply when a backend task exposes high-volume user actions, user-generated content, reports, bans, or trust and safety workflows.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-plan, bx-code, bx-fix, bx-test, bx-review
  sources: OWASP API4 Unrestricted Resource Consumption 2023; OWASP API6 Unrestricted Access to Sensitive Business Flows 2023; OWASP Automated Threats to Web Applications
---

# Abuse prevention and moderation

## Khi nào dùng

Dùng cho registration/login, follow, invite, like, comment, message, upload,
report, block, ban và user-generated content có nguy cơ spam/harassment/automation.

## Nội dung

1. Liệt kê asset, actor và abuse case theo từng business flow: spam, scraping,
   enumeration, brute force, mass follow/report, upload flood và permission abuse.
   Chốt tác động và tín hiệu có thể đo trước khi chọn control.
2. Đặt quota/rate theo nhiều dimension phù hợp: actor, device/install, IP/network,
   target/resource và global capacity. Không dựa riêng IP; trả lỗi/retry metadata
   không làm lộ threshold nhạy cảm.
3. Mutation cần idempotency/replay protection, validation và resource budget.
   Queue/worker cũng phải có per-tenant/user fairness để một actor không chiếm hết.
4. Định nghĩa rõ block, mute, report, hide, remove, suspend, ban và appeal; state
   transition có actor/reason/time/audit. Block phải tác động query/feed/realtime/
   notification chứ không chỉ UI.
5. Tách evidence moderation khỏi nội dung public; giới hạn quyền xem, retention,
   redaction và deletion. Không đưa raw report/private content vào log hoặc prompt.
6. Automated score chỉ là signal trừ khi policy phê duyệt auto-action. Có manual
   review/appeal cho hành động ảnh hưởng lớn và chống mass-report manipulation.
7. Test boundary/quota reset, distributed concurrency, alternate identity,
   duplicate report, blocked interactions, moderator authorization, audit, appeal
   và fail-safe khi dependency moderation lỗi.

Ví dụ ngắn:

    POST /users/{id}/follow: per-actor + per-target + global budget, idempotent edge.
    Block user: revoke feed/realtime/push visibility và tạo audit event.

## Chống chỉ định / giới hạn

- Không coi CAPTCHA, IP block hoặc một ML score là biện pháp duy nhất.
- Không cho moderator bypass tenant/scope hoặc sửa audit trail.
- Không chạy pentest/traffic abuse lên production hoặc external target khi chưa
  được cấp quyền rõ ràng.
