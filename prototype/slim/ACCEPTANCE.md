# Tiêu chí nghiệm thu prototype Slim

Prototype được kiểm tra ở hai lớp. Kiểm tra tĩnh chứng minh cấu hình sinh ra ổn
định và đúng policy. Kiểm tra live chứng minh hành vi thật của OpenCode và
OpenChamber; PASS tĩnh không bao giờ thay thế evidence live.

## Kiểm tra offline

| ID | Yêu cầu |
|---|---|
| O1 | Pin package, commit, integrity, schema SHA-256 của Slim và compatibility OpenCode SDK; tắt auto-update. |
| O2 | Registry có đúng bảy role user-facing: alias `bx-director` là primary; sáu specialist `bx-*` là mode `all`; raw `orchestrator` là subagent ẩn. |
| O3 | Mỗi role giữ đúng model `provider/model` do user chọn. |
| O4 | Effective permission cho parent chạy background task, cấm specialist tự delegate, bảo vệ path ngoài project và chặn edit/bash mutation của role read-only. BX Test dùng ownership + review để giới hạn source vì test path phụ thuộc framework. |
| O5 | Mỗi role có allowlist 2-5 skill rõ ràng; không role nào nhận toàn bộ catalog. |

## Kiểm tra live

| ID | Yêu cầu |
|---|---|
| L1 | `oh-my-opencode-slim doctor` chấp nhận config exact 2.2.13; `biexce slim doctor` PASS registry bridge và isolated launcher; từng role khởi chạy đúng actual runtime model mà không nạp plugin legacy. |
| L2 | Canary edit của role read-only bị chặn, BX Code sửa file trong project thành công, path ngoài project vẫn qua permission UI. |
| L3 | Task backend chỉ load được skill đã gán; skill không liên quan không khả dụng. |
| L4 | OpenChamber cho chọn trực tiếp đủ bảy role user-facing, không hiện Director legacy trùng; child native vẫn hiện role/model và chuyển `busy` sang terminal. |
| L5 | Hai child read-only độc lập cùng ở trạng thái `busy` trong một khoảng thời gian và cả hai kết quả quay về parent. |
| L6 | Writer không trùng ownership được chạy song song; writer trùng file được tuần tự hóa hoặc cô lập có chủ đích, không mất thay đổi. |
| L7 | Sau reconnect/restart, child còn live vẫn running, terminal result được reconcile, child mất thành stopped/unreconciled trước một lần re-dispatch an toàn. Không sửa state thủ công. |

## Fixture live

Dùng workspace tạm sạch gồm hai module read-only, hai output writer độc lập và
một tình huống tranh chấp file chung. Trong case restart, ngắt một read lane và
một writer lane. Evidence phải giữ session ID, timestamp, actual model,
permission decision, terminal result và final diff.

Chạy L1-L7 hai lần từ workspace sạch. Step 1 chỉ được nghiệm thu khi O1-O5 và cả
hai lần live đều PASS mà không cài đè, xóa hoặc sửa runtime user-global cũ.

Tài liệu tham khảo:

- <https://github.com/alvinunreal/oh-my-opencode-slim/blob/v2.2.13/docs/configuration.md>
- <https://github.com/alvinunreal/oh-my-opencode-slim/blob/v2.2.13/docs/background-orchestration.md>
