---
name: performance
description: Diagnose and improve backend performance from a reproducible workload, baseline, profile, budget, and before-after evidence. Apply when latency, throughput, resource use, or capacity is an acceptance concern.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-code, bx-fix, bx-test, bx-review
  sources: Google SRE service level objectives and monitoring; OpenTelemetry concepts and metrics; PostgreSQL current EXPLAIN documentation
---

# Backend performance

## Khi nào dùng

Dùng khi có SLO/budget, regression, capacity risk hoặc evidence thực tế. Nếu chỉ là phỏng đoán “có thể chậm”, đo trước khi tối ưu.

## Nội dung

1. Chốt workload: endpoint/job, data volume, concurrency, environment, warm/cold state và success condition.
2. Dùng mục tiêu người dùng làm SLI/SLO; đo latency theo percentile phù hợp, throughput, error và resource. Không chỉ dùng average.
3. Tạo baseline lặp lại được; lưu tool/command, version/config, samples và biến động.
4. Profile để tìm bottleneck trước khi sửa: CPU/allocation, I/O, lock/queue, network/dependency và database plan.
5. Với query, dùng `EXPLAIN`/runtime evidence trên dữ liệu đại diện; kiểm tra rows estimate, scan/index, sort, join, lock và query count.
6. Sửa một nguyên nhân có giả thuyết; giữ correctness/security và đặt giới hạn cho cache, queue, batch, retry, payload.
7. Chạy lại cùng workload; so sánh before/after, tail latency, errors và chi phí resource. Thêm regression test/budget khi ổn định.
8. Instrument traces/metrics/logs có correlation nhưng kiểm soát cardinality; không dùng user ID/raw URL làm metric label tùy tiện.

Ví dụ ngắn:

```text
Workload: list runs của một owner với dữ liệu đại diện.
Baseline: p50/p95/p99 + DB calls + CPU.
Hypothesis: missing composite index.
Verify: same dataset/load, same correctness, query plan và percentiles mới.
```

## Chống chỉ định / giới hạn

- Không đặt ngưỡng hiệu năng tùy ý; lấy từ acceptance/SLO hoặc baseline được duyệt.
- Không benchmark môi trường khác rồi tuyên bố production đạt.
- Không cache/denormalize trước khi xác định invalidation, consistency, memory và security impact.
