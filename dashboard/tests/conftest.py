import os
import sys

# Cho phép `import app...` dù chạy pytest từ đâu.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Ép chế độ mock để test chạy offline, không cần opencode serve.
os.environ.setdefault("BIEXCE_DASHBOARD_MOCK", "1")
