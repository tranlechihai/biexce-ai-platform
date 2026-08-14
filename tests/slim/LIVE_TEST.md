# Quy trình live acceptance Step 1

Chỉ chạy sau khi dependency Slim đã được cài vào config test cô lập. Không dùng
workspace source và không đổi user-global.

## Chuẩn bị

1. Tạo config từ `prototype/slim/build_config.py` bằng routing cần test.
2. Copy `tests/slim/fixtures/live-smoke` sang workspace tạm mới.
3. Khởi động OpenCode/OpenChamber với:

```text
OPENCODE_CONFIG_DIR=<isolated-config>
OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS=true
```

Trên Windows, không truyền prompt nhiều đoạn qua shim `opencode.cmd`: đối số có
thể bị cắt tại dòng trống. Dùng executable trực tiếp hoặc prompt một dòng, rồi
kiểm tra lại user message đã lưu trong parent session trước khi chấm kết quả.

Giữ session ID, timestamp, actual model, permission decision và final diff làm
evidence. Chạy toàn bộ matrix hai lần với workspace sạch.

## Lần 1 — Role và permission

- Mở parent `BX-Director`.
- Gọi lần lượt đủ sáu specialist bằng task nhỏ đúng vai trò.
- Xác nhận UI hiện đúng parent/child, display name và actual model.
- BX Explore thử tạo `explore-canary.txt`: phải bị tool permission chặn.
- BX Code tạo `outputs/code-canary.txt`: phải thành công.
- Một agent thử ghi ngoài workspace: phải hiện permission UI; chọn Deny và xác
  nhận không có file ngoài project.

## Lần 2 — Parallel và ownership

Gửi parent một yêu cầu duy nhất:

```text
Chạy BIEXCE Step 1 acceptance bằng background agents.

1. Cho BX Explore đọc module-a/input.txt và BX Review đọc module-b/input.txt
   song song; cả hai chỉ trả evidence.
2. Sau khi cả hai terminal, cho hai BX Code child độc lập chạy song song:
   lane A tạo outputs/a.txt chứa đúng ALPHA-OUTPUT; lane B tạo outputs/b.txt
   chứa đúng BETA-OUTPUT.
3. Sau đó có hai yêu cầu cùng sửa shared.txt: thêm dòng FIRST rồi thêm dòng
   SECOND. Không cho hai writer sửa shared.txt đồng thời; phải tuần tự hóa hoặc
   cô lập rồi tích hợp mà không mất dòng BASE.
4. Reconcile toàn bộ kết quả và báo session ID, model, thời gian bắt đầu/kết
   thúc, final diff. Không tạo scheduler/state/lock BIEXCE riêng.
```

PASS khi hai read child và hai writer độc lập có khoảng `busy` chồng nhau;
`outputs/a.txt`, `outputs/b.txt` đúng nội dung; `shared.txt` chứa BASE, FIRST và
SECOND đúng một lần; không có thay đổi ngoài workspace.

## Lần 3 — Restart/reconcile

- Bắt đầu lại bài test parallel trên workspace sạch.
- Restart OpenCode/plugin khi một read child và một writer đang `busy`.
- Sau reconnect, ghi nhận hành vi thật: child còn live, terminal result có sẵn,
  hay stopped/unreconciled.
- Chỉ PASS nếu Director tiếp tục hoặc re-dispatch an toàn đúng một lần từ
  evidence/checkpoint, không sửa JSON, clear lock hoặc bắt user gọi specialist.

Slim 2.2.13 không được giả định tự resume chỉ vì config tĩnh hợp lệ. Nếu case
này không PASS, ghi rõ giới hạn upstream và không xóa runtime BIEXCE cũ.

## Step 3 — Recovery và policy tổng quát

Dùng ít nhất hai project/fixture khác nhau; không thêm task ID hoặc path của
fixture vào source prompt/runtime. Với `fixtures/resilience-python`, kiểm tra:

1. Requirement mới làm test cũ `todo` trở nên obsolete; BX Test cập nhật test
   minh bạch thay vì block project.
2. Hai task cùng ownership `taskboard/status.py` được tuần tự hóa; task ở
   `taskboard/summary.py` có thể chạy song song khi dependency cho phép.
3. User đổi thêm một canonical status tại Gate 1; Director cập nhật plan và tiếp
   tục, không yêu cầu state edit hay recovery command.
4. Dừng OpenCode khi writer đang chạy rồi mở lại cùng config/workspace; workflow
   reconcile native session và chỉ chạy phần còn thiếu.
5. Provider/child lỗi tạm thời được phân loại là infrastructure incident; khi
   provider trở lại, workflow tiếp tục từ TODO/checkpoint hiện có.

PASS chỉ khi source regression xanh, Gate 2 hoàn tất, không có custom lock/state,
và không cần user gọi specialist thủ công.

Evidence của mỗi lần chạy phải ghi đúng phạm vi. Một project đi từ Brief
đến Gate 2 chỉ chứng minh E2E run đó; không được suy diễn thành restart,
provider recovery hoặc khả năng tổng quát cho project thứ hai nếu chưa chạy.
Run cloud đầu tiên được lưu tại
`evidence/step3-resilience-run-1.json`.

Project thứ hai dùng `fixtures/resilience-node` để tránh chỉ kiểm tra một
ngôn ngữ hoặc một bộ path. Run này phải kết hợp restart khi writer đang
busy và một provider interruption có thể phục hồi. Chỉ phần việc chưa
hoàn tất được dispatch lại; không được sửa state hay gọi specialist
thủ công.

Evidence của project Node nằm tại
`evidence/step3-resilience-run-2.json`. Run này PASS Gate 2, chạy hai writer
song song, giữ nguyên công việc sau restart và xử lý thay đổi hậu Gate 1 bằng
một adjustment lane. Provider interruption và đúng tình huống restart khi
writer đang busy vẫn được giữ lại cho acceptance hybrid trên Ubuntu; evidence
không được suy diễn hai case này là đã PASS.
