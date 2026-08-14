# Baseline và ranh giới chuyển đổi

[← Tổng quan kiến trúc](OPENCODE-SLIM-BIEXCE.md)

## Runtime hiện tại

Runtime cũ được đóng băng tại nhánh archive. Trong baseline phát hành, phần
authority cũ còn nằm ở:

- `src/global/plugins/biexce-control.js`;
- `src/biexce_control/autopilot.py`;
- `src/biexce_control/workflow.py`;
- các lệnh CLI Autopilot;
- schema state liên quan.

Chỉ loại bỏ các thành phần đó sau khi prototype Slim vượt acceptance matrix.
Không tiếp tục sửa hoặc mở rộng custom scheduler hiện tại và không viết một
scheduler BIEXCE mới.

## Nguyên tắc giữ baseline

- Đóng băng custom scheduler/runtime hiện tại.
- Lưu source và test baseline; không xóa runtime cũ.
- Pin version OpenCode/OpenChamber đang dùng.
- Không cài Slim global nếu chưa có user approval.
- Không sửa hoặc xóa runtime production/user-global trong giai đoạn prototype.
- Duy trì rollback bundle của baseline cũ đến khi migration hoàn tất.

## Compatibility contract của prototype

| Thành phần | Baseline quan sát | Prototype yêu cầu |
|---|---:|---:|
| OpenCode CLI | 1.18.4 | kiểm thử với family 1.18.13 |
| `@opencode-ai/plugin` | 1.18.4 | 1.18.13 |
| `@opencode-ai/sdk` | không pin trong BIEXCE | 1.18.13 |
| Slim | chưa cài | 2.2.13 exact |

Slim được pin tại:

- package: `oh-my-opencode-slim@2.2.13`;
- commit: `781ca04fb83dbcd73a262c19ca70533ebbc117d2`;
- auto-update: tắt trong release.

Slim 2.2.13 dùng native background subagents còn mang cờ experimental.
Prototype phải chạy với:

```text
OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS=true
```

Compatibility gap này là điều kiện live acceptance, không được âm thầm nâng
user-global.

## Ranh giới prototype

Prototype dùng workspace/config test riêng và phải xác minh:

- compatibility giữa OpenCode hiện hành và SDK mà Slim pin;
- OpenCode native background subagents hoạt động;
- mapping đủ bảy BIEXCE role;
- model cloud/local và permission;
- child hiển thị trong OpenChamber;
- hai task độc lập chạy song song;
- giới hạn restart của bản Slim stable.

Không xem job board in-memory là bằng chứng resume thành công.

## Liên kết tiếp theo

- [Kiến trúc đích](TARGET-ARCHITECTURE.md)
- [Kế hoạch migration](MIGRATION.md)
- [Acceptance bắt buộc](ACCEPTANCE.md)
