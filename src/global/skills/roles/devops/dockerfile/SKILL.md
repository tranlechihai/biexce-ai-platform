---
name: dockerfile
description: Author minimal, reproducible, non-root container definitions with pinned inputs and explicit runtime contracts. Apply when a task adds or changes Dockerfile or Compose configuration.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-code, bx-fix, bx-review
  sources: Docker official build best practices; Dockerfile reference and build checks; NIST Secure Software Development Framework
---

# Dockerfile

## Khi nào dùng

Dùng để viết/review container config. Đây là authoring skill; agent không deploy, push image hoặc thay production runtime nếu chưa được giao rõ.

## Nội dung

1. Chọn base image nhỏ, phù hợp runtime và pin version/digest theo policy; ghi kế hoạch cập nhật thay vì dùng tag mơ hồ.
2. Multi-stage build để tách toolchain khỏi runtime; chỉ copy artifact/dependency cần thiết.
3. Sắp layer để cache hiệu quả, dùng `.dockerignore`, không copy repository/secret rộng hơn cần thiết.
4. Chạy non-root, filesystem/read-only/capability tối thiểu khi platform hỗ trợ; không bake credential vào ARG/ENV/layer.
5. Pin dependency bằng lockfile, build deterministic và fail sớm khi thiếu input.
6. `ENTRYPOINT`/`CMD`, port, healthcheck, signal và graceful shutdown phải khớp contract ứng dụng.
7. Compose dành cho topology dev/test; config/secret đi từ runtime injection và có file example an toàn.
8. Chạy build check/lint và smoke start đã tài liệu hóa; scan image khi pipeline có công cụ được duyệt.

Ví dụ: builder cài lockfile và build binary; runtime distroless/non-root chỉ nhận binary, expose health endpoint và không chứa package manager.

## Chống chỉ định / giới hạn

- Không chạy deploy, registry push, prune hoặc thay production orchestration.
- Không dùng secret qua `COPY`, `ARG` hoặc commit `.env` thật.
- Không thêm Compose/Kubernetes nếu task chỉ cần local process và repo chưa dùng container.
