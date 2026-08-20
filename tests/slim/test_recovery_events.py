from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "src" / "global" / "slim" / "plugins" / "biexce-recovery.js"


class RecoveryEventTests(unittest.TestCase):
    def test_recovery_is_event_driven_and_not_one_shot(self):
        content = PLUGIN.read_text(encoding="utf-8")
        for event in (
            'event.type === "server.connected"',
            'event.type === "session.idle"',
            'event.type === "session.error"',
            'event.type === "session.status"',
            'event.type === "todo.updated"',
        ):
            self.assertIn(event, content)
        self.assertIn("const seen = new Set()", content)
        self.assertNotIn("let completed", content)

    def test_recovery_uses_debounce_and_bounded_retry(self):
        content = PLUGIN.read_text(encoding="utf-8")
        self.assertIn("clearTimeout(timer)", content)
        self.assertIn("failures < 2", content)
        self.assertIn("{ seen }", content)


if __name__ == "__main__":
    unittest.main()
