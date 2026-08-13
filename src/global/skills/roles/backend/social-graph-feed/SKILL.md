---
name: social-graph-feed
description: Design and implement social relationships, privacy-aware feed queries, stable pagination, and consistency rules. Apply when a backend task touches follow, friend, block, mute, profile visibility, timeline, or feed ranking.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-plan, bx-code, bx-fix, bx-test, bx-review
  sources: Android Developers offline-first architecture and Paging guidance; PostgreSQL current index and transaction documentation; OWASP API Security Top 10 2023
---

# Social graph and feed

## Khi nào dùng

Dùng khi thiết kế hoặc thay đổi quan hệ người dùng, quyền xem nội dung, feed hoặc
pagination của social backend. Chỉ thêm ranking/fan-out phức tạp khi requirement
hoặc số liệu tải chứng minh cần thiết.

## Nội dung

1. Chốt loại edge và state transition: follow một chiều, friend hai chiều,
   request/accept, block và mute. Đặt invariant unique(actor,target,type), cấm
   self-edge khi nghiệp vụ không cho phép và xử lý request lặp idempotent.
2. Tạo ma trận actor x relationship x resource x visibility; block luôn thắng
   follow/friend. Thực thi authorization ở cả mutation lẫn query/feed, không lọc
   riêng ở client.
3. Xác định source of truth cho edge, post và counter. Counter/cache là dữ liệu
   dẫn xuất, phải có cách rebuild/reconcile và không quyết định quyền truy cập.
4. Chọn feed candidate, filter privacy, ranking và tie-breaker rõ. Dùng cursor
   opaque theo ordering bất biến như (rank_key, created_at, id); không dùng
   offset cho timeline thay đổi liên tục.
5. Bắt đầu bằng fan-out-on-read/query đơn giản. Chỉ chuyển sang fan-out-on-write,
   materialized timeline hoặc cache khi đã đo volume, celebrity/hot-key, latency
   và yêu cầu consistency; luôn có invalidation khi block/delete/privacy đổi.
6. Dùng transaction/outbox cho thay đổi cần phát event; consumer phải idempotent.
   Xác định behavior khi post bị xóa, account khóa hoặc relationship đổi giữa hai
   trang feed.
7. Test ownership/privacy, block precedence, duplicate edge, concurrent follow,
   stable cursor, no duplicate/missing item trong cùng snapshot và cache stale.

Ví dụ ngắn:

    Feed newest-first: cursor encode(created_at,id); query nhỏ hơn tuple cursor.
    Trước khi trả item: kiểm author visibility và block theo cả hai chiều.

## Chống chỉ định / giới hạn

- Không suy ra privacy từ việc ID khó đoán hoặc client không hiển thị nội dung.
- Không thêm graph database, queue hoặc ranking service khi relational query và
  index hiện tại chưa được đo là không đủ.
- Không hứa feed toàn cục có thứ tự tuyệt đối nếu contract chỉ đảm bảo per-user
  hoặc eventual consistency.
