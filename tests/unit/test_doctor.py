import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
from unittest import mock
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPOSITORY_ROOT / 'scripts' / 'biexce_linux.py'
SPEC = importlib.util.spec_from_file_location('biexce_linux', MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DoctorTests(unittest.TestCase):
    def test_source_passes_and_pending_dependencies_warn(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'not-installed'
            output = io.StringIO()
            with (
                mock.patch.object(MODULE, 'opencode_prefix', return_value=None),
                mock.patch.object(
                    MODULE.socket,
                    'create_connection',
                    side_effect=OSError('offline'),
                ),
                contextlib.redirect_stdout(output),
            ):
                MODULE.doctor(REPOSITORY_ROOT, target)
        text = output.getvalue()
        self.assertIn('Source contract: PASS', text)
        self.assertIn('Agents: 7', text)
        self.assertIn('Installed target: WARN', text)
        self.assertIn('OpenCode CLI: WARN', text)
        self.assertIn('Bifrost endpoint: WARN', text)


if __name__ == '__main__':
    unittest.main()
