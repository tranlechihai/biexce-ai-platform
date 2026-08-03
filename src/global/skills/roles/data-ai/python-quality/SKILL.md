---
name: python-quality
description: Implement typed, testable, deterministic Python modules with clear boundaries, dependency hygiene, and actionable errors. Apply on Python application, automation, or data tasks.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-code, bx-fix, bx-review
  sources: Python PEP 8 and typing documentation; Python packaging user guide; pytest good integration practices
---

# Python quality

## Khi nào dùng

Dùng khi sửa Python. Đọc `pyproject.toml`, supported Python, formatter/linter/type checker và package layout hiện có trước; không áp một toolchain mới ngoài scope.

## Nội dung

1. Module/function có một trách nhiệm và dependency direction rõ; tách I/O khỏi logic thuần khi giúp test.
2. Type hint cho public boundary và cấu trúc dữ liệu quan trọng; không dùng `Any` để che contract chưa hiểu.
3. Tên/format/import theo cấu hình dự án và PEP 8; không format hàng loạt file không liên quan.
4. Resource dùng context manager; exception cụ thể, giữ cause và message có action nhưng không lộ secret.
5. Không dùng mutable default/global state ẩn; time/random/environment được inject hoặc kiểm soát trong test.
6. Dependency pin qua cơ chế dự án, không dùng `setup.py test`; tránh package mới nếu stdlib/hiện có đủ.
7. Path, encoding và subprocess cross-platform; argument list thay shell string, validate untrusted input.
8. Test unit/integration phù hợp, chạy formatter/lint/type/test đã tài liệu hóa và báo exact result.

Ví dụ: parser thuần trả dataclass typed; file reader chịu trách nhiệm UTF-8/error mapping; tests dùng fixture tạm và cleanup tự động.

## Chống chỉ định / giới hạn

- Không thêm mypy/ruff/pytest hoặc đổi package layout chỉ để “chuẩn hóa” nếu repo chưa chọn.
- Không bắt rộng `Exception` rồi bỏ qua hoặc trả success.
- Không ghi cache/temp vào source tree nếu có thể dùng thư mục tạm quản lý vòng đời.
