"""The optional CLI probe must fail before installing unreadable hook config."""
import subprocess
from pathlib import Path
import unittest
from unittest.mock import patch

from lcu.codex_hooks import require_cli_hook_support


class CodexCliCapabilityTests(unittest.TestCase):
    def test_missing_cli_keeps_before_install_setup_available(self):
        with patch('lcu.codex_hooks.shutil.which', return_value=None), \
             patch('lcu.codex_hooks.subprocess.run') as run:
            require_cli_hook_support({'PATH': '/bin'})
            run.assert_not_called()

    def test_unsupported_cli_fails_with_isolated_no_auth_probe(self):
        calls = []

        def run(argv, **kwargs):
            calls.append((argv, kwargs))
            self.assertNotIn('OPENAI_API_KEY', kwargs['env'])
            self.assertEqual(kwargs['env']['HOME'], kwargs['env']['CODEX_HOME'])
            if argv[-1] == '--version':
                return subprocess.CompletedProcess(argv, 0, 'codex-cli 0.145.0\n', '')
            self.assertIn('mcp_tool', Path(kwargs['env']['CODEX_HOME'], 'config.toml').read_text())
            return subprocess.CompletedProcess(argv, 1, '', 'unknown variant mcp_tool')

        with patch('lcu.codex_hooks.shutil.which', return_value='/fixture/bin/codex'), \
             patch('lcu.codex_hooks.subprocess.run', side_effect=run):
            with self.assertRaisesRegex(ValueError, r'/fixture/bin/codex \(codex-cli 0\.145\.0\)'):
                require_cli_hook_support({'PATH': '/fixture/bin', 'OPENAI_API_KEY': 'never-forward'})
        self.assertEqual(len(calls), 2)


if __name__ == '__main__':
    unittest.main()
