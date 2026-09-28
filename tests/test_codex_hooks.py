"""CODEX_HOME selection matches the native CLI's nullish-coalescing choice."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lcu.codex_hooks import _selected_codex_home, require_cli_hook_support


class CodexHomeTests(unittest.TestCase):
    def test_absent_codex_home_defaults_to_dot_codex(self):
        self.assertEqual(_selected_codex_home({'HOME': '/home/a'}), Path('/home/a/.codex'))

    def test_explicit_codex_home_is_kept(self):
        self.assertEqual(_selected_codex_home({'HOME': '/home/a', 'CODEX_HOME': '/x/c'}),
                         Path('/x/c'))

    def test_empty_codex_home_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'CODEX_HOME is set but empty'):
            _selected_codex_home({'HOME': '/home/a', 'CODEX_HOME': ''})

    def test_require_cli_hook_support_rejects_empty_codex_home(self):
        # The guard fires before probing for a codex executable on PATH.
        with self.assertRaisesRegex(ValueError, 'CODEX_HOME is set but empty'):
            require_cli_hook_support({'HOME': '/home/a', 'CODEX_HOME': '', 'PATH': ''})


if __name__ == '__main__':
    unittest.main()
