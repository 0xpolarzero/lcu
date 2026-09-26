"""Recognize the original Codex CLI locations shipped by supported apps."""

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lcu.app_layout import locate_codex_tools


class CodexApplicationLayoutTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.resources = Path(temporary.name) / 'Resources'
        self.resources.mkdir()

    def _add_pair(self, relative, suffix=''):
        cli = self.resources / relative / f'codex{suffix}'
        host = self.resources / relative / f'codex-code-mode-host{suffix}'
        cli.parent.mkdir(parents=True, exist_ok=True)
        cli.write_text('original Codex CLI')
        host.write_text('original code-mode host')
        return cli, host

    def test_resolves_legacy_and_relocated_original_pairs(self):
        for relative in (Path('.'), Path('codex-cli/bin')):
            with self.subTest(relative=relative):
                with tempfile.TemporaryDirectory() as temporary:
                    self.resources = Path(temporary) / 'Resources'
                    self.resources.mkdir(parents=True)
                    cli, host = self._add_pair(relative)
                    selected = locate_codex_tools(self.resources)
                    self.assertEqual((selected.cli, selected.code_mode_host), (cli, host))

    def test_resolves_windows_executables(self):
        cli, host = self._add_pair(Path('codex-cli/bin'), '.exe')
        selected = locate_codex_tools(self.resources, windows=True)
        self.assertEqual((selected.cli, selected.code_mode_host), (cli, host))

    def test_rejects_partial_and_symlinked_layouts(self):
        cli, _ = self._add_pair(Path('codex-cli/bin'))
        (self.resources / 'codex-cli/bin/codex-code-mode-host').unlink()
        legacy_cli, _ = self._add_pair(Path('.'))
        legacy_cli.unlink()
        with self.assertRaisesRegex(ValueError, 'complete original Codex CLI layout'):
            locate_codex_tools(self.resources)

        cli.parent.mkdir(parents=True, exist_ok=True)
        external = self.resources.parent / 'external-codex'
        external.write_text('outside app')
        cli.unlink()
        cli.symlink_to(external)
        (cli.parent / 'codex-code-mode-host').write_text('host')
        with self.assertRaisesRegex(ValueError, 'complete original Codex CLI layout'):
            locate_codex_tools(self.resources)

    def test_rejects_ambiguous_complete_layouts(self):
        self._add_pair(Path('.'))
        self._add_pair(Path('codex-cli/bin'))
        with self.assertRaisesRegex(ValueError, 'Ambiguous original Codex CLI layout'):
            locate_codex_tools(self.resources)


if __name__ == '__main__':
    unittest.main()
