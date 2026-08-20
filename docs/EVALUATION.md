# Đánh giá workflow BIEXCE Plan/Build

## Mục tiêu

`biexce eval` biến một lần chạy OpenCode/OpenChamber thành scorecard có thể so
sánh. Công cụ chỉ đọc evidence, không chạy command trong project, không sửa source
và không duy trì scheduler hay state riêng.

Evidence mặc định nằm ngoài project:

- Linux/macOS: `$XDG_STATE_HOME/biexce/evals` hoặc `~/.local/state/biexce/evals`.
- Windows: `%LOCALAPPDATA%\biexce\evals`.
- Có thể đổi bằng biến `BIEXCE_EVAL_HOME`.

Raw prompt, nội dung source và credential không được ghi vào report. Session export
chỉ được rút thành model, token, thời gian, tool call, lỗi và compaction.
Report tách `wall-clock duration` của toàn workflow khỏi `total agent time`, nên
agent chạy song song không làm thời gian hoàn thành bị cộng trùng.

## 1. Thu evidence của project

Chờ session về idle rồi export parent và các child quan trọng:

```bash
mkdir -p "$HOME/.local/state/biexce/eval-input"

opencode export <session-id> \
  > "$HOME/.local/state/biexce/eval-input/session.json"
```

Sinh JUnit bằng test runner của project. Ví dụ Python:

```bash
.venv/bin/python -m pytest -q \
  --junitxml="$HOME/.local/state/biexce/eval-input/pytest.xml"
```

Tạo assessment machine-local, không commit vào project:

```json
{
  "completion_status": "completed",
  "human_interventions": 0,
  "scope_violations": 0,
  "test_weakened": false,
  "critical_security_findings": 0,
  "checks": [
    {"name": "ruff", "status": "PASS"},
    {"name": "compile", "status": "PASS"},
    {"name": "browser-smoke", "status": "PASS"}
  ],
  "notes": "Plan cloud, Build local; no manual source repair."
}
```

Trạng thái check hợp lệ: `PASS`, `FAIL`, `INCONCLUSIVE`, `SKIPPED`.

Thu report:

```bash
biexce eval collect \
  --project "$HOME/workspace/biexce-social-backend-slim" \
  --session-export "$HOME/.local/state/biexce/eval-input/session.json" \
  --junit "$HOME/.local/state/biexce/eval-input/pytest.xml" \
  --assessment "$HOME/.local/state/biexce/eval-input/assessment.json" \
  --label social-backend-baseline \
  --json
```

Có thể lặp `--session-export` và `--junit`. Nếu evidence chưa đủ, verdict phải là
`INCONCLUSIVE`; công cụ không tự đoán kết quả.

## 2. Chấm lại

```bash
biexce eval score --run <run-directory> --json
```

Hard gates:

1. Công việc hoàn thành.
2. Check/test bắt buộc không fail.
3. Không sửa ngoài scope.
4. Không làm yếu test.
5. Không còn security finding nghiêm trọng.

Score gồm product 50, autonomy 25, efficiency 15 và evidence 10. Candidate cần
đạt hard gates và tối thiểu 85/100.

## 3. So baseline với candidate

Chạy cùng task/dataset với cấu hình candidate, sau đó:

```bash
biexce eval compare \
  --baseline <baseline-run> \
  --candidate <candidate-run> \
  --output "$HOME/.local/state/biexce/eval-comparisons/social" \
  --json
```

`PROMOTE` chỉ xuất hiện khi candidate `PASS` và score không thấp hơn baseline.
Thời gian, tool failure và human intervention được báo riêng để không che regression.

## Quy tắc sử dụng trong công ty

- Không dùng một project duy nhất để kết luận workflow dùng được cho mọi dự án.
- Mỗi candidate chạy ít nhất hai lần trên bugfix nhỏ, feature trung bình và một
  project tích hợp backend/UI.
- Tách lỗi product, prompt/skill, model, permission/tool, session, provider và
  environment trước khi sửa.
- Chỉ sửa workflow khi root cause có tính tổng quát; không thêm task ID, filename
  hoặc ngoại lệ riêng để làm một fixture pass.
- Không commit raw session export vì nó có thể chứa source hoặc dữ liệu nội bộ.
