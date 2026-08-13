# Danh mục agent và skill BIEXCE

Đây là danh mục chuẩn của 7 agent và 59 skill. Không tạo bản sao agent/skill
ở thư mục khác; installer lấy trực tiếp danh sách và hash từ
`src/harness-manifest.json`.

## Cấu trúc chuẩn

```text
src/global/
├─ agents/                       7 hợp đồng vai trò
└─ skills/
   ├─ core/                      workflow dùng chung
   ├─ roles/<discipline>/        kỹ năng IT tổng quát theo chuyên môn
   ├─ company/                   knowledge/policy riêng của BIEXCE
   └─ _TEMPLATE/SKILL.md         nguồn tạo skill, không được cài như skill
```

Mỗi skill là một thư mục lowercase-kebab-case chỉ chứa `SKILL.md` và resource
thực sự cần thiết. Tài liệu vận hành, catalog và changelog nằm ở `docs/`, không
đặt README phụ trong từng skill.

## Agent

| Agent | Chế độ | Trách nhiệm chính | Quyền ghi |
| --- | --- | --- | --- |
| `bx-director` | primary | điều phối B1-B5, gate, state, WIP=1 | chỉ `.biexce/**` |
| `bx-plan` | all | Brief, PRD, kiến trúc, plan và task contract | chỉ artifact kế hoạch |
| `bx-explore` | all | khảo sát repo, tạo Codebase Brief | chỉ artifact Codebase Brief |
| `bx-code` | all | triển khai task đã duyệt và focused test | source trong writable scope |
| `bx-fix` | all | root-cause và patch tối thiểu từ evidence | source trong fix scope |
| `bx-test` | all | build/test, evidence và verdict | không sửa source |
| `bx-review` | all | review plan/diff/security và verdict | read-only |

Model không nằm trong file agent. User gán độc lập cho từng agent bằng
`provider/model`; data policy và permission vẫn áp dụng riêng.

## Mức độ sẵn sàng của skill

| Nhóm | Skill | Trạng thái |
| --- | --- | --- |
| Core | `task-spec`, `state-beacon`, `evidence-format`, `review-verdict`, `codebase-brief` | ready |
| Core | `design-discovery`, `systematic-debugging`, `test-driven-development` | ready; điều chỉnh có chọn lọc từ `obra/superpowers` |
| Core | `biexce-delivery`, `git-flow-ai` | draft; không dùng làm authority cho tới khi được duyệt |
| Planning/BA | `prd`, `user-story`, `acceptance-criteria`, `estimate` | ready |
| Architecture | `system-design`, `adr`, `api-contract`, `data-model` | ready |
| Backend | `api-design`, `database-migration`, `auth-security`, `testing-backend`, `performance` | ready |
| Backend mạng xã hội/mobile | `social-graph-feed`, `media-upload-delivery`, `push-notification-delivery`, `realtime-event-delivery`, `mobile-offline-sync`, `abuse-moderation` | ready; chỉ nạp khi task liên quan |
| QA | `test-strategy`, `unit-integration-e2e`, `regression`, `browser-exploratory` | ready |
| Frontend | `component-patterns`, `state-management`, `styling`, `accessibility`, `testing-frontend` | ready |
| Android | `kotlin-gradle`, `testing-android` | ready |
| iOS | `swift-xcode`, `testing-ios` | ready |
| Unity | `unity-project-rules`, `editmode-playmode-tests` | ready |
| DevOps | `dockerfile`, `ci-config`, `env-config` | ready |
| Security | `secure-coding`, `owasp-review` | ready |
| Tài liệu | `readme`, `api-docs`, `changelog`, `report` | ready |
| Data/AI | `python-quality`, `eval-harness` | ready |
| Company | `definition-of-done`, `security-policy` | ready baseline |
| Company | `conventions`, `git-policy` | skeleton; cần organization policy thật |

Tổng: 59 skill, gồm 55 `ready`, 2 `draft`, 2 `skeleton`; toàn bộ 45 generic
role skill đã `ready`. `browser-exploratory` là capability tùy chọn của
`bx-test`, chỉ nạp khi criterion cần browser/GUI thật. Skill skeleton không
được dùng làm authority và agent
không được tự bịa phần company knowledge còn thiếu.

## Quy trình bảo trì

1. Sửa role tại `src/global/agents/<id>.md`; đồng bộ RACI trong
   `docs/AGENT-ROLES.md` nếu trách nhiệm thay đổi.
2. Sửa skill tại đúng `src/global/skills/<group>/<name>/SKILL.md`; không nhân bản.
3. Chạy `python -B scripts/validate_skills.py`.
4. Chạy `python -B scripts/update_manifest.py`, rồi `--check`.
5. Chạy unit, integration và package regression trước release.

Installer cài agent/skill user-global vào `~/.config/opencode`; project knowledge
tiếp tục nằm trong `AGENTS.md` gần nhất và `.biexce/`. Knowledge search/RAG nội
bộ là giai đoạn sau, không trộn vào 59 skill hiện tại.

Các skill điều chỉnh từ dự án bên thứ ba được ghi nguồn trong frontmatter và
[`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md). BIEXCE không cài lớp
orchestration của Superpowers; runtime BIEXCE vẫn là workflow authority duy nhất.
