---
name: evidence-format
description: Standardized verification evidence. Apply when BX Test reports check results, when BX Fix/BX Code claim something works, or when any agent cites a command result.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-test, bx-fix, bx-code, bx-review, bx-director
  sources: harness 0.3.x test contract; scorecard benchmark docs cũ
---

# Evidence Format

## Fresh verification trước completion

- Lệnh chứng minh phải được chạy lại trong working tree và môi trường hiện tại,
  sau thay đổi cuối cùng có liên quan. Kết quả từ phiên cũ không đủ để claim `PASS`.
- Agent phải đọc exit code và output thực, không suy luận từ việc command có vẻ chạy.
- Trong Autopilot, lệnh kiểm chứng chạy qua `biexce_run_command`; evidence ghi
  exit code, duration và `OUTPUT_TRUNCATED`. Output bị giới hạn không được suy
  diễn thành PASS nếu dòng chứng minh kết quả đã bị cắt.
- Nếu không thể chạy, dùng `INCONCLUSIVE` và nêu chính xác dependency/environment còn
  thiếu; không thay bằng dự đoán.
- Với generated manifest/hash, chạy cả generator/check theo contract trước khi handoff.
- Evidence chỉ liên quan một criterion; log dài được rút gọn nhưng không được bỏ dòng
  chứng minh failure hoặc số lượng test.

Nguyên tắc bất di bất dịch: **không có evidence thì không được nói "đã
pass"** — chỉ được nói "chưa kiểm chứng" kèm lý do.

## Bảng criteria → check (bx-test bắt buộc)

```markdown
| Criterion | Check | Kết quả |
|---|---|---|
| C1 <tóm tắt> | `<lệnh>` | PASS (exit 0, 12/12 tests) |
| C2 <tóm tắt> | đọc file X có hàm Y | PASS (path:line) |
| C3 <tóm tắt> | KHÔNG KIỂM ĐƯỢC | lý do (thiếu env/VPN/hạ tầng) |
```

## Bảng quality pipeline (bx-test bắt buộc)

Ghi đúng thứ tự bên dưới. Chỉ `N/A` khi project thật sự không có gate hoặc
task không thể ảnh hưởng gate đó; một command tồn tại nhưng thiếu môi trường là
`NOT_RUN` và verdict `INCONCLUSIVE`.

```markdown
| Gate | Command | Kết quả |
|---|---|---|
| Format check | `<command>` | PASS / FAIL / N/A — reason |
| Lint/static | `<command>` | PASS / FAIL / N/A — reason |
| Typecheck | `<command>` | PASS / FAIL / N/A — reason |
| Unit/focused | `<command>` | PASS / FAIL / N/A — reason |
| Integration/contract/E2E | `<command>` | PASS / FAIL / N/A — reason |
| Build/package | `<command>` | PASS / FAIL / N/A — reason |
```

## Khối evidence cho một lệnh

```text
$ <lệnh đúng nguyên văn>
exit: <code> · thời gian: <s nếu có>
<3–10 dòng output quan trọng nhất — KHÔNG dán cả log>
```

## Phân loại khi FAIL (bắt buộc chọn một)

`patch` (do thay đổi trong phiên/task hiện tại; phải có diff hoặc baseline chứng minh) ·
`pre-existing` (đã hỏng trước phiên/task hiện tại) ·
`environment` · `missing-dependency` · `infra-unavailable`.

Tên file, comment như `intentional bug`/`smoke-test bug`, hoặc mục đích của
fixture không phải bằng chứng rằng lỗi do patch hiện tại. Nếu evidence nói lỗi
đã tồn tại trước phiên và không có diff ngược lại, dùng `pre-existing`.

Quyết định theo thứ tự:

1. Có diff/baseline chứng minh thay đổi trong task hoặc phiên hiện tại gây ra
   failure? Có → `patch`.
2. Failure đã được quan sát trước task/phiên hiện tại, hoặc không có bằng chứng
   cho bước 1? → `pre-existing`.

Nhãn mô tả **nguồn gốc failure**, không mô tả việc agent sắp tạo một patch.

## Verdict cuối

`PASS` (mọi criterion có check đạt) · `FAIL` (≥1 criterion rớt, ghi rõ cái
nào) · `INCONCLUSIVE` (không đủ điều kiện kiểm — liệt kê phần chưa kiểm).
Kèm mục "Chưa kiểm": danh sách + lý do. Verdict không có bảng criteria là
verdict không hợp lệ.
