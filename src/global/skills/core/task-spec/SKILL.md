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
Verify: `<lệnh đã có trong repo/Brief — không bịa lệnh>`

## 4. Boundaries
Owner role: <đúng một role bx-code | bx-fix | bx-test | ...>
Writable files: <glob/đường dẫn được phép sửa; `none` nếu read-only>
Read-only inputs: <test/spec/file chỉ dùng làm evidence>
Out-of-scope: <những thứ dễ bị lôi vào nhưng CẤM làm>
Depends on: <t-IDs> · Effort: S|M|L
```

## Quy tắc

- Task phải **độc lập thực thi được** và **vừa một lần review** — thà nhiều
  task nhỏ còn hơn một task lớn.
- Acceptance criteria phải kiểm chứng được (lệnh, file tồn tại, hành vi cụ
  thể) — "code sạch đẹp" không phải criterion.
- Lời giao việc trong chat (director → agent) dùng đúng 4 mục rút gọn:
  objective / expected output / owner + writable/read-only boundaries /
  out-of-scope.
- Mỗi task có đúng một owner role. Failure đã có reproduction/evidence thuộc
  `bx-fix`; feature mới thuộc `bx-code`; verification thuộc `bx-test`. Không
  giao chung một task cho nhiều owner.
- Với defect đã có failing test, test đó là **read-only evidence** mặc định:
  chỉ source fix nằm trong `Writable files`. Chỉ cho sửa/thêm test khi
  objective nói rõ test thiếu hoặc requirement/test đã được người có thẩm
  quyền xác nhận cần đổi.
- Không đổi expected result để khớp implementation. Nếu test hiện hữu yêu cầu
  hành vi xung đột với requirement, đánh dấu blocker và escalate; không tự
  chọn code hay test là đúng.

## Chống chỉ định

Không dùng cho câu hỏi vặt hoặc việc 1 file rõ ràng ở chế độ Daily — đừng
bureaucratize việc nhỏ (effort scaling).
