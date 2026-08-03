---
name: security-policy
description: Classify BIEXCE data into Zones A/B/C and enforce where agents, models, tools, logs, and artifacts may send it. Apply before reading repo data, calling a model/tool, creating prompts, or exporting evidence.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: all
  sources: BIEXCE agent role and permission contracts; OWASP ASVS 5.0; OWASP Secrets Management Cheat Sheet
---

# Security policy — Zone A/B/C

## Khi nào dùng

Dùng trước mọi data flow: agent đọc file, chưng cất brief, gọi local/cloud model, dùng tool/plugin, ghi log/evidence hoặc copy artifact. Company policy có ưu tiên cao nhất và project không được override để nới quyền.

## Nội dung

| Zone | Dữ liệu | Đích mặc định |
|---|---|---|
| A | source code, diff, nội dung file/repo, raw log có chi tiết nội bộ | chỉ local/company infrastructure đã duyệt |
| B | brief/PRD/plan/task spec/error summary đã chưng cất, không chứa source/secret | local; cloud provider đã duyệt khi policy/model binding cho phép |
| C | secret, key/token/password, credential, signing material, production personal/sensitive data | không gửi vào model/prompt/log; chỉ secret store và runtime đích được duyệt |

Quy trình bắt buộc:

1. Phân loại theo mức nhạy cảm cao nhất trong payload; không “rửa zone” chỉ bằng đổi tên file.
2. Giảm dữ liệu: chỉ đọc/gửi phần cần cho task, redact identifier và nội dung không cần thiết.
3. Source chỉ đi qua agent local có permission. Khi cần cloud, bx-explore tạo artifact Zone B bằng mô tả hành vi/contract/error summary, không dán source/diff.
4. Kiểm tra provider, model binding, destination và tool/plugin trước call; destination không rõ thì dừng.
5. Zone C phát hiện trong input/output phải dừng hành động liên quan, không lặp lại giá trị; báo loại secret và vị trí khái quát để owner rotate/xử lý.
6. Evidence/log giữ tối thiểu, redact token/header/query/payload nhạy cảm; áp retention/access policy của công ty.
7. Temporary cloud exception cho Zone A chỉ hợp lệ khi chủ dự án phê duyệt rõ provider, scope, thời hạn và rủi ro; mặc định vẫn deny và không agent nào tự cấp ngoại lệ.

Ví dụ ngắn:

```text
Raw stack trace chứa đường dẫn/code line: Zone A -> local.
Summary “installer thiếu 1 managed skill, hash mismatch”: Zone B -> có thể cloud.
API key trong .env: Zone C -> không đưa vào prompt; redact và báo owner.
```

## Chống chỉ định / giới hạn

- Không gửi Zone A lên cloud vì model local chậm hoặc chưa sẵn sàng.
- Không đọc/echo Zone C để “kiểm tra xem có thật không”.
- Không tin cam kết của plugin/provider thay cho permission và phê duyệt công ty.
