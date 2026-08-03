---
name: state-management
description: Select ownership, lifecycle, and synchronization rules for frontend state while minimizing duplicated and derived state. Apply when a UI task adds or changes client-side state.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-code, bx-fix, bx-review
  sources: React official Managing State and Sharing State guidance; Redux official style guide; WHATWG URL standard
---

# State management

## Khi nào dùng

Dùng khi thêm state, đồng bộ nhiều màn hình, cache server data, hoặc sửa lỗi stale/race. Xác định state thuộc URL, server, component, form hay toàn ứng dụng trước khi chọn công cụ.

## Nội dung

1. Chọn một source of truth; không lưu lại giá trị có thể tính rẻ và chắc chắn từ props/state khác.
2. Giữ state cục bộ mặc định; nâng lên owner chung gần nhất chỉ khi nhiều consumer thật sự cần.
3. State điều hướng, filter chia sẻ hoặc deep-link nên nằm trong URL với encode/decode và default rõ.
4. Phân biệt server state với client state; dùng cơ chế fetch/cache sẵn có, không copy response sang store khác vô cớ.
5. Với async, định nghĩa loading/empty/success/error và cách hủy hoặc bỏ qua response cũ để tránh race.
6. Update immutable; gom transition liên quan thành action/reducer khi nhiều field phải đổi nguyên tử.
7. Persist chỉ dữ liệu cần sống qua phiên; version schema, xử lý dữ liệu cũ/hỏng và không persist secret.
8. Test transition và user-visible result; thêm regression cho race, refresh hoặc restore khi liên quan.

Ví dụ: bộ lọc danh sách dùng query string làm nguồn thật; dữ liệu API ở cache; modal mở/đóng giữ local trong screen.

## Chống chỉ định / giới hạn

- Không thêm global store cho state chỉ có một owner.
- Không dùng effect để đồng bộ hai bản sao của cùng dữ liệu nếu có thể derive trực tiếp.
- Không đưa credential, token hoặc dữ liệu nhạy cảm vào local storage.
