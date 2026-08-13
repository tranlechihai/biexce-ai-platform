---
name: definition-of-done
description: Enforce the company-wide completion gate for every BIEXCE task and increment. Apply before any agent declares work done, ready for review, or release-ready.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: all
  sources: Scrum Guide 2020; Scrum.org Definition of Done and acceptance criteria guidance; BIEXCE evidence-format and review-verdict
---

# Definition of Done

## Khi nào dùng

Dùng ở mọi handoff và trước từ “done/pass/release-ready”. Acceptance criteria là điều kiện riêng của hạng mục; DoD là chuẩn chất lượng chung và phải đạt cả hai.

## Nội dung

Một task chỉ `DONE` khi tất cả mục áp dụng đều có evidence:

1. **Scope:** acceptance criteria đạt; out-of-scope và thay đổi ngoài kế hoạch được báo rõ.
2. **Code/config:** đúng structure/convention, không để TODO debug/dead code ngoài scope; generated manifest/hash đồng bộ.
3. **Quality:** pipeline áp dụng được đã chạy theo thứ tự format check →
   lint/static → typecheck → focused/unit → integration/contract/E2E →
   build/package; regression theo blast radius pass. Gate không tồn tại phải
   ghi `N/A` có lý do; gate tồn tại nhưng không chạy được là `INCONCLUSIVE`,
   không phải `DONE`. Skipped/unchecked được liệt kê, không che flaky.
4. **Security/data:** permission default-deny giữ nguyên; không secret; Zone A/B/C và auth/input/logging được kiểm khi liên quan.
5. **Compatibility:** contract, migration, installer/package và platform/version support được kiểm theo impact.
6. **Operations:** error/observability, rollout, rollback/recovery và change notes có khi thay đổi runtime/production.
7. **Documentation:** user/dev/runbook/task state cập nhật khi behavior hoặc thao tác thay đổi.
8. **Evidence:** bảng criterion→check, exact command/exit từ lần chạy mới sau thay đổi
   cuối, các phần chưa kiểm và verdict `PASS|FAIL|INCONCLUSIVE`.
9. **Review/gate:** bx-review không còn blocker; human approval/merge/deploy gate hoàn tất nếu plan yêu cầu.

Trạng thái dùng thống nhất:

- `DONE`: mọi gate áp dụng đạt.
- `INCONCLUSIVE`: thiếu môi trường/dependency để kiểm; không đồng nghĩa pass.
- `BLOCKED`: cần thẩm quyền hoặc external state.
- `PARTIAL`: chỉ giao được phần scope, phải nêu phần còn lại.

Ví dụ ngắn:

```text
Code + unit PASS nhưng chưa chạy package/install matrix:
INCONCLUSIVE, chưa DONE. Owner: bx-test; unblock: chạy integration suite.
```

## Chống chỉ định / giới hạn

- Không hạ DoD theo từng task để kịp tiến độ. Ngoại lệ phải do người có thẩm quyền chấp thuận, ghi phạm vi/rủi ro/hạn xử lý.
- Không đồng nhất “đã code xong” với “done” hoặc “đã deploy”.
- Không dùng nhận xét chủ quan thay evidence kiểm chứng.
