"""Parser cho state beacon `[BX-STATE] {...}` (core skill `state-beacon`).

Dùng chung cho Flow board: dashboard chỉ theo dõi trạng thái thực thi qua các dòng
beacon này + PROJECT_STATE.json. Sai format = mất realtime, nên parser phải
chặt đúng như quy tắc skill: một dòng, không code-fence, JSON hợp lệ có `project`.
"""
import json
import re

# Đúng quy tắc skill state-beacon: ^\[BX-STATE\] \{.*\}$ (một dòng).
BEACON_RE = re.compile(r"^\[BX-STATE\] (\{.*\})$")

VALID_STATUS = {
    "backlog", "planning", "coding", "testing",
    "fixing", "reviewing", "done", "escalated",
}
REQUIRED_KEYS = {
    "project", "stage", "task", "status", "round",
    "done", "total", "agent",
}
ALLOWED_KEYS = REQUIRED_KEYS | {"note"}


def parse_beacon(line):
    """Trả về dict beacon nếu hợp lệ, None nếu không.

    Từ chối: nhiều dòng, nằm trong code fence, JSON hỏng, thiếu `project`.
    """
    if not isinstance(line, str):
        return None
    line = line.strip()
    match = BEACON_RE.match(line)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    if (
        not isinstance(data, dict)
        or not REQUIRED_KEYS.issubset(data)
        or not set(data).issubset(ALLOWED_KEYS)
    ):
        return None
    if not isinstance(data["project"], str) or not data["project"].strip():
        return None
    if not isinstance(data["stage"], str) or not re.fullmatch(
        r"B[1-5]", data["stage"]
    ):
        return None
    task = data["task"]
    if task is not None and (
        not isinstance(task, str) or not re.fullmatch(r"t-[0-9]{3}", task)
    ):
        return None
    if data["status"] not in VALID_STATUS:
        return None
    if (
        isinstance(data["round"], bool)
        or not isinstance(data["round"], int)
        or not 0 <= data["round"] <= 3
    ):
        return None
    done, total = data["done"], data["total"]
    if any(
        isinstance(value, bool) or not isinstance(value, int)
        for value in (done, total)
    ):
        return None
    if done < 0 or total < 0 or done > total:
        return None
    agent = data["agent"]
    if agent is not None and (
        not isinstance(agent, str) or not agent.startswith("bx-")
    ):
        return None
    note = data.get("note")
    if note is not None and (not isinstance(note, str) or len(note) > 80):
        return None
    return data
