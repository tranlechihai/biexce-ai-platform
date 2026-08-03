# BIEXCE Mission Control

Mission Control là dashboard chỉ đọc dành cho các dự án BIEXCE và phiên làm
việc OpenCode. Dashboard hiển thị trạng thái task và Autopilot, agent đang hoạt
động, model đã cấu hình và model thực tế, mức sử dụng token/chi phí, event đã
lọc và telemetry hạ tầng tùy chọn.

Dashboard không điều khiển Autopilot và không tham gia quyết định Human Gate.
Mỗi panel đều ghi rõ nguồn dữ liệu, máy, thời điểm và chất lượng dữ liệu. Nếu
không có dữ liệu live, dashboard sẽ báo không khả dụng thay vì dùng dữ liệu
mock thay thế.

## Chạy bằng fixture offline

```powershell
cd dashboard
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8090
```

Mở `http://127.0.0.1:8090`. Chế độ offline dùng dữ liệu xác định sẵn và không
gọi OpenCode, model endpoint hoặc hạ tầng công ty.

## Chạy với dữ liệu OpenCode live

Khởi động OpenCode API trên cùng máy tin cậy:

```text
opencode serve --hostname 127.0.0.1 --port 4096
```

Thiết lập biến môi trường của dashboard rồi khởi động ứng dụng. Ví dụ trên
Windows:

```powershell
$env:BIEXCE_DASHBOARD_MOCK = '0'
$env:OPENCODE_SERVE_URL = 'http://127.0.0.1:4096'
$env:BIEXCE_PROJECT_ROOTS = 'D:\work\project-a;D:\work\project-b'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8090
```

Trên Linux và macOS, dùng ký tự phân cách path của hệ điều hành khi khai báo
nhiều project root. Xem `.env.example` để biết toàn bộ thiết lập được hỗ trợ.

## Nguồn dữ liệu

- OpenCode `/session` và `/session/status`: agent, trạng thái busy/idle/retry,
  model thực tế, token usage và chi phí.
- `.biexce/state/PROJECT_STATE.json`: task, trạng thái, WIP và số vòng fix.
- `.biexce/state/AUTOPILOT_CONTROL.json`: chế độ điều khiển.
- `.biexce/state/AUTOPILOT_WORKFLOW.json`: phase, task hiện tại, agent kế tiếp
  và Human Gate.
- OpenCode `/event`: event đã chuẩn hóa, không chứa prompt thô hoặc tool input
  thô.
- BIEXCE model routing: model đã cấu hình để so sánh với model thực tế.

## API

| Endpoint | Mục đích |
| --- | --- |
| `GET /healthz` | Chế độ, nguồn dữ liệu và phiên bản |
| `GET /api/overview` | Tổng hợp agent, task, token và chi phí |
| `GET /api/flow` | Dự án, task và workflow Autopilot |
| `GET /api/sessions` | Các phiên OpenCode đã chuẩn hóa |
| `GET /api/usage` | Mức sử dụng theo model, agent và dự án |
| `GET /api/hardware` | Telemetry phần cứng và model-serving tùy chọn |
| `GET /api/events` | Server-sent event đã lọc |

`GET /api/quota` được giữ lại làm alias tương thích cho `/api/usage`.

## Kiểm tra

Chạy từ thư mục gốc của repository:

```text
python -B -m pytest dashboard/tests -q -p no:cacheprovider
```

Bộ test chỉ sử dụng fixture, không yêu cầu VPN hoặc quyền truy cập model.

## Yêu cầu khi triển khai production

Trước khi mở Mission Control ra ngoài loopback, cần có:

- xác thực và phân quyền;
- TLS qua reverse proxy đã được phê duyệt;
- allowlist dự án rõ ràng;
- giới hạn quyền truy cập OpenCode API;
- chính sách che dữ liệu nhạy cảm và lưu log;
- collector chỉ đọc cho GPU, model-serving và usage nếu bật các panel này.

Không bind development server vào mạng LAN công ty hoặc public internet.
