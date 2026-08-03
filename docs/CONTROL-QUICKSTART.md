# Hướng dẫn nhanh điều khiển BIEXCE

Sau khi installer chạy thành công, mở terminal mới. Windows, Ubuntu/Linux và
macOS đều dùng cùng command `biexce` từ mọi folder.

## Thiết lập lần đầu trên một máy

Kết nối provider bằng `/connect` trong OpenCode. Xem model bằng `/models`
hoặc:

```text
biexce model list
```

Danh sách này tách riêng model thấy trong catalog, trạng thái credential của
provider và trạng thái inference. Model xuất hiện trong catalog không đồng nghĩa
provider đã đăng nhập hoặc inference đã chạy thành công.

Model ID phải đúng dạng `provider/model`. Gắn model cho 7 agent:

```text
biexce setup
```

Kiểm tra:

```text
biexce status
biexce model validate
biexce self-test
```

`status` cần hiển thị `Routing: READY (7/7 agents)` và
`Runtime guard: READY`. Nếu provider báo `NOT AUTHENTICATED`, dùng `/connect`
trong OpenCode rồi chạy lại kiểm tra. Cảnh báo này không chặn user chọn hoặc
apply model. `self-test --live-inference` mới gửi request inference thật.
Restart OpenCode sau khi thay đổi model routing.

## Bật và tắt Auto cho project hiện tại

Mở terminal tại folder project:

```text
biexce auto on
```

`auto on` dùng folder hiện tại làm project root, kiểm tra runtime/model, chuyển
`OFF → ON_IDLE → ARMED → RUNNING` và khởi tạo workflow ở `EXPLORE`. Nếu
project đã có workflow chưa hoàn tất, lệnh tiếp tục từ state hiện có.

Sau đó mở cùng folder bằng OpenCode, chọn `Bx-Director` và gửi mục tiêu,
constraints, definition of done. Tắt Auto:

```text
biexce auto off
```

State và artifact được giữ trong `.biexce/` của project để kiểm tra hoặc tiếp
tục về sau.

## Human Gate trong OpenCode

Workflow bắt buộc:

```text
EXPLORE → PLAN → PLAN_REVIEW → WAITING_GATE_1
  → CODE → TEST ─FAIL→ FIX → TEST
                └PASS→ TASK_REVIEW ─CHANGES REQUIRED→ FIX
                                    └APPROVE→ task kế tiếp
  → INTEGRATION_TEST → INTEGRATION_REVIEW → WAITING_GATE_2 → COMPLETE
```

Khi đến `WAITING_GATE_1` hoặc `WAITING_GATE_2`, Director gọi control tool và
OpenCode hiển thị yêu cầu xác nhận ngay trong Desktop/TUI:

- Approve: Gate được ghi nhận và Director tự tiếp tục bước kế tiếp.
- Reject: workflow giữ nguyên ở Gate; không có state approval nào được ghi.
- Gate 2 được approve: workflow chuyển `COMPLETE` và Auto tự về `OFF`.

User không phải chạy lệnh approve trong terminal. Gate 1 vẫn kiểm tra Brief,
Plan, 3–5 task contract, DAG, WIP=1, permissions và routing trước khi cho phép
code.

Không khởi động OpenCode bằng `--auto`: chế độ đó tự duyệt các permission đang
ở trạng thái ask. BIEXCE Auto là `biexce auto on` và độc lập với auto-approve
của OpenCode.

## Lệnh kiểm tra và điều khiển phụ

```text
biexce auto status
biexce auto check
biexce auto pause
biexce status
biexce self-test
```

- `auto status`: xem mode, phase, agent kế tiếp và task hiện tại.
- `auto check`: kiểm tra đầy đủ project artifacts và runtime.
- `auto pause`: giữ state nhưng chặn delegation mới.
- `self-test`: test offline control plane và tự xóa fixture tạm.
- `self-test --live-inference`: kiểm tra thêm model thật khi đã có VPN.

Dùng `--project <path>` chỉ khi muốn điều khiển một project khác folder hiện
tại.

## Desktop và TUI

- Desktop: mở project, chọn `Bx-Director` trong agent selector và gửi yêu cầu.
- TUI: mở `opencode` tại project, nhấn `Tab` để chọn `Bx-Director`.
- Composer/response hiển thị agent và model đang chạy.
- Daily Assist vẫn dùng bình thường khi Auto là `OFF`; delegation đa-agent chỉ
  được mở khi project ở `RUNNING`.

Mỗi project có state riêng. Hai cửa sổ OpenCode mở cùng project vẫn bị giới hạn
WIP=1 bằng project-local lock.
