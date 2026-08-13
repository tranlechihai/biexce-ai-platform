---
name: task-spec
description: The Biexce story-file standard. Apply when writing a task file (bx-plan), delegating any work between agents (bx-director), or executing a task (bx-code/bx-fix) - every task and every delegation must follow the four-part spec.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-director, bx-plan, bx-code, bx-fix, bx-test
  sources: Anthropic multi-agent lessons (4-part delegation); BMAD story files; github/spec-kit tasks
---

# Task Spec — story file 4 phần

Lý do tồn tại: lỗi số 1 của hệ multi-agent production là handoff mơ hồ →
agent làm trùng, làm sai, hoặc phình phạm vi. Mọi task file và mọi lời giao
việc giữa agent PHẢI đủ 4 phần dưới đây. Thiếu phần nào, agent nhận việc có
quyền hỏi lại thay vì đoán.

## Định dạng file `.biexce/tasks/t-NNN.md`

```markdown
# t-012 — <một dòng mục tiêu>

## 1. Objective
<Kết quả cần đạt, nói theo hành vi quan sát được, không nói theo cách làm.>

## 2. Context tối thiểu
<Cái gì đã tồn tại để dựa vào (đường dẫn, interface, quyết định từ MASTER_PLAN).
Đủ để dev local-context-nhỏ làm được MÀ KHÔNG cần đọc cả repo.>

## 3. Acceptance criteria
- [ ] <tiêu chí kiểm được — map vào lệnh test/lệnh chạy nếu có>
- [ ] <…>
Verify: `<lệnh thực thi được từ repo/Brief hoặc catalog test-strategy; không dùng N/A>`

Quality pipeline (dùng command có thật; ghi `N/A — <lý do>` nếu không áp dụng):
- Format check: `<command | N/A — reason>`
- Lint/static: `<command | N/A — reason>`
- Typecheck: `<command | N/A — reason>`
- Unit/focused: `<command | N/A — reason>`
- Integration/contract/E2E: `<command | N/A — reason>`
- Build/package: `<command | N/A — reason>`

## 4. Boundaries
Owner role: <bx-code cho implementation; bx-test chỉ cho verification-only>
Writable files: <glob/đường dẫn được phép sửa; `none` nếu read-only>
Read-only inputs: <test/spec/file chỉ dùng làm evidence>
Out-of-scope: <những thứ dễ bị lôi vào nhưng CẤM làm>
Depends on: <t-IDs> · Effort: S|M|L
```

## Quy tắc

- Task phải **độc lập thực thi được** và **vừa một lần review** — thà nhiều
  task nhỏ còn hơn một task lớn.
- Mỗi task nên hoàn tất trong một phiên làm việc tập trung. Nếu phải thay nhiều subsystem
  hoặc không thể mô tả một output kiểm chứng được, tách task trước khi delegate.
- Acceptance criteria phải kiểm chứng được (lệnh, file tồn tại, hành vi cụ
  thể) — "code sạch đẹp" không phải criterion.
- Quality pipeline phải lấy từ `AGENTS.md`, package/build scripts, CI hoặc
  tài liệu hiện hữu; khi stack được khai báo rõ thì được dùng deterministic
  command catalog trong `qa-testing/test-strategy`. Không có công cụ tương ứng
  thì từng category có thể ghi `N/A` cùng lý do, nhưng dòng `Verify` của task
  luôn phải là một lệnh thực thi được. Không dùng `N/A` để né một gate đang tồn tại.
- Lời giao việc trong chat (director → agent) dùng đúng 4 mục rút gọn:
  objective / expected output / owner + writable/read-only boundaries /
  out-of-scope.
- Mỗi task có đúng một owner role. Failure đã có reproduction/evidence thuộc
  `bx-fix`; feature mới thuộc `bx-code`; verification thuộc `bx-test`. Không
  giao chung một task cho nhiều owner.
- Task `Owner role: bx-test` phải là verification-only. Dùng
  `Writable files: none` hoặc chỉ khai báo evidence dưới
  `.biexce/reports/**`; runtime route thẳng đến `TEST/bx-test`, không tạo job
  `CODE/bx-code`. BX Test không được sửa source/test code.
- Với defect đã có failing test, test đó là **read-only evidence** mặc định:
  chỉ source fix nằm trong `Writable files`. Chỉ cho sửa/thêm test khi
  objective nói rõ test thiếu hoặc requirement/test đã được người có thẩm
  quyền xác nhận cần đổi.
- Không đổi expected result để khớp implementation. Nếu test hiện hữu yêu cầu
  hành vi xung đột với requirement, đánh dấu blocker và escalate; không tự
  chọn code hay test là đúng.
- Khi cách triển khai không hiển nhiên, Context tối thiểu phải ghi rõ file/interface sẽ
  dùng, thứ tự thay đổi và test cần chạy. Không dùng placeholder kiểu “implement logic”
  hoặc “add validation” mà không nêu contract quan sát được.
- Trước khi giao task, scan placeholder/TODO trong task file và xác nhận đường dẫn/lệnh
  thật sự tồn tại hoặc được task trước tạo ra.

## Chống chỉ định

Không dùng cho câu hỏi vặt hoặc việc 1 file rõ ràng ở chế độ Daily — đừng
bureaucratize việc nhỏ (effort scaling).
