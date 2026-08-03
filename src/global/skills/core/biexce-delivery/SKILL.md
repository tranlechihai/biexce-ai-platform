---
name: biexce-delivery
description: The Biexce delivery contract for both modes - Daily assist routing and Autopilot five-stage SOP. Apply when delivering or validating any coding task at Biexce.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: draft
  applies_to: all bx agents
  sources: harness 0.3.13 biexce-delivery; MetaGPT SOP chain; github/spec-kit; BMAD-METHOD (chưng cất)
---

# Biexce Delivery — hợp đồng giao việc chung

## Luôn luôn (mọi agent, mọi chế độ)

- Đọc `AGENTS.md` gần nhất + artifact liên quan trước khi làm.
- Bảo toàn công việc của user; ở trong repo được duyệt; không đụng secrets,
  generated, vendor, production.
- Chỉ dùng lệnh đã có nguồn (repo docs/Brief); không bịa lệnh, không nhận
  "đã pass" khi thiếu evidence (`evidence-format`).
- Phạm vi bounded: làm đúng việc được giao, báo thiếu thay vì tự mở rộng.
- Model/effort do user hoặc cấu hình chọn — agent không tự đổi.
- Git: theo `git-flow-ai`; agent không ghi Git nếu chưa có company policy và
  permission tường minh.

## Chế độ 1 — Daily assist (user gọi thẳng agent)

BX Code là mặc định: việc rõ → làm luôn; chỉ gọi đúng một agent phụ khi bản
chất việc cần (plan-only/rủi ro cao → bx-plan; check-only → bx-test;
review-only → bx-review). Không ép pipeline cho việc nhỏ.

## Chế độ 2 — Autopilot (user chọn BX Director, giao cả dự án)

SOP 5 bước, artifact là nguồn sự thật (`.biexce/`):

| Bước | Chủ trì | Artifact ra | Gate |
|---|---|---|---|
| B1 Kickoff | director | PROJECT_BRIEF.md | — |
| B2 Plan | bx-plan (+bx-explore Brief; bx-review red-team) | MASTER_PLAN.md + tasks/t-NNN.md | **GATE 1: người duyệt plan** |
| B3 Execute | director điều phối code→test→(fix≤3)→review từng task, TUẦN TỰ (WIP=1 baseline) | code + reports/ | — |
| B4 Integrate | bx-test regression + bx-review tổng | INTEGRATION_REPORT.md | — |
| B5 Handover | director | FINAL_REPORT.md | **GATE 2: người nghiệm thu** |

Kỷ luật B3: story file là toàn bộ phạm vi của dev; trần 3 vòng fix rồi
escalate; mọi chuyển trạng thái phát `state-beacon`; director re-drive task
treo thay vì bỏ qua.

## Hoàn thành (mọi chế độ)

Báo cáo: outcome trước → file đổi → lệnh/kết quả → phần chưa kiểm → rủi ro
còn lại. Gọn đủ dùng hằng ngày.
