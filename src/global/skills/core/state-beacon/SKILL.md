---
name: state-beacon
description: The BX-STATE progress beacon format. Apply whenever BX Director changes any task's state - the dashboard and humans track projects only through these lines and PROJECT_STATE.json.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: ready
  applies_to: bx-director
  sources: thiết kế nội bộ Biexce (dashboard Mission Control)
---

# State Beacon

## Khi nào dùng

BX Director phát beacon **sau MỖI thay đổi trạng thái** (task đổi cột, đổi
vòng fix, đổi stage, escalate) và khi bắt đầu/kết thúc một stage.

## Định dạng (một dòng, không code-fence, không văn xuôi bao quanh)

`[BX-STATE] {"project":"<id>","stage":"B1..B5","task":"t-NNN|null","status":"backlog|planning|coding|testing|fixing|reviewing|done|escalated","round":0,"done":N,"total":M,"agent":"bx-code|...","note":"<=80 ký tự"}`

- JSON một dòng, key đúng tên trên, `note` tùy chọn.
- Đồng thời cập nhật `.biexce/state/PROJECT_STATE.json`:

```json
{
  "project": "social-backend",
  "stage": "B3",
  "updated": "<ISO8601>",
  "tasks": [
    {"id": "t-001", "title": "scaffold", "status": "done", "round": 0, "agent": null},
    {"id": "t-002", "title": "auth", "status": "fixing", "round": 2, "agent": "bx-fix"}
  ]
}
```

## Quy tắc

- Dashboard parse bằng regex `^\[BX-STATE\] \{.*\}$` — sai format là mất
  realtime; không viết beacon trong code fence, không xuống dòng giữa JSON.
- `done/total` tính theo task ở trạng thái `done` trên tổng task của plan.
- Không nhét nội dung source/secret vào `note`.
