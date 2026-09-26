"""Windows setup selects the registered app's exact platform instructions."""

import json
import os
from pathlib import Path
import tempfile
from contextlib import nullcontext
from types import SimpleNamespace
import unittest
from unittest import mock
import subprocess
import sys

from lcu import setup


class WindowsSetupTests(unittest.TestCase):
    @unittest.skipIf(os.name == 'nt', 'This decoder fixture uses a POSIX executable shebang')
    def test_node_installer_output_decodes_under_legacy_windows_locale(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            home = base / 'home'
            home.mkdir()
            node = base / 'node-fixture'
            node.write_text('#!' + sys.executable + '\n'
                            'import json,sys\n'
                            'args=sys.argv[1:]\n'
                            'if args and args[0].endswith("skills.mjs"):\n'
                            '  print(json.dumps([{"name":"lcu","status":"installed"}]))\n'
                            '  sys.stderr.buffer.write(b"note \\xe2\\x80\\x8f\\n")\n'
                            'elif any("upsertServer" in arg for arg in args):\n'
                            '  print(json.dumps({"path":"' + str(base / 'mcp.json').replace('\\', '\\\\') + '"}))\n')
            node.chmod(0o755)
            skill = base / 'skill'
            skill.mkdir()
            adapter = base / 'adapters/claude.mjs'
            adapter.parent.mkdir()
            adapter.write_text('fixture relay')
            with mock.patch.object(setup, 'installer_paths', return_value=(node, base / 'skills.mjs', base / 'mcp.mjs')), \
                 mock.patch.object(setup, 'generate_skill', return_value=skill), \
                 mock.patch.object(setup, 'installed_app_resources', return_value=base / 'resources'), \
                 mock.patch.object(setup, 'host_policy', return_value={}), \
                 mock.patch('subprocess._text_encoding', return_value='cp1252'):
                failures = setup.configure(['claude-code'], home, skill, ['lcu'], base / 'tools', base,
                                           environ={'HOME': str(home), 'PATH': str(base)})
            self.assertEqual(failures, [])

    def test_codex_hooks_use_original_platform_executable(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            resources = base / 'app/resources'
            release = base / 'release'
            (release / 'adapters').mkdir(parents=True)
            (release / 'adapters/codex.mjs').write_text('fixture relay')
            (release / 'adapters/audio-files.mjs').write_text('fixture helper')
            config = base / 'account/config.toml'
            config.parent.mkdir()
            for system, expected in (('win32', 'codex.exe'), ('linux', 'codex'), ('darwin', 'codex')):
                def registered(argv, **_options):
                    output = ('[{"name":"lcu","status":"installed"}]' if ' add ' in f' {" ".join(map(str, argv))} '
                              else json.dumps({'path': str(config)}))
                    return subprocess.CompletedProcess(argv, 0, output, '')
                with self.subTest(system=system), \
                     mock.patch.object(setup.sys, 'platform', system), \
                     mock.patch.object(setup, 'installer_environment', return_value={'PATH': 'fixture'}), \
                     mock.patch.object(setup, 'installer_paths', return_value=(base / 'node', base / 'skills', base / 'mcp')), \
                     mock.patch.object(setup, 'generate_skill', return_value=base / 'skill'), \
                     mock.patch.object(setup, 'installed_app_resources', return_value=resources), \
                     mock.patch.object(setup, 'host_policy', return_value={}), \
                     mock.patch.object(setup.subprocess, 'run', side_effect=registered), \
                     mock.patch('lcu.codex_hooks.require_cli_hook_support'), \
                     mock.patch('lcu.codex_hooks.install_hooks') as hooks:
                    self.assertEqual(setup.configure(['codex'], config.parent, base / 'skill',
                        ['lcu'], base / 'tools', release), [])
                    self.assertEqual(hooks.call_args.args[0], resources / expected)

    def test_linux_discover_setup_keeps_version_probe_on_direct_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            prefix = Path(temporary).resolve() / 'lcu'
            binary = prefix / 'current/bin/lcu'
            session = prefix / 'current/bin/lcu-session'
            binary.parent.mkdir(parents=True)
            for path in (binary, session):
                path.write_text('fixture')
                path.chmod(0o755)
            account = SimpleNamespace(pw_name='fixture', pw_uid=os.getuid(), pw_dir=str(prefix.parent))
            with mock.patch.object(setup.sys, 'platform', 'linux'), \
                 mock.patch.object(setup, 'validate', return_value=(account, ['codex'])), \
                 mock.patch.object(setup, 'installer_environment'), \
                 mock.patch.object(setup, 'installer_paths'), \
                 mock.patch.object(setup, 'setup_lock', return_value=nullcontext()), \
                 mock.patch.object(setup, 'configure', return_value=[]), \
                 mock.patch.object(setup.subprocess, 'run') as run:
                setup.main(['--prefix', str(prefix), '--agent', 'codex', '--session', 'discover', '--yes'])
            self.assertEqual(run.call_args_list[0].args[0], [str(binary), '--version'])

    def test_registered_windows_account_and_direct_session_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary).resolve()
            with mock.patch.object(setup.sys, 'platform', 'win32'), \
                 mock.patch.dict(os.environ, {'USERPROFILE': str(home)}, clear=False):
                args = setup.parser().parse_args(['--prefix', str(home / 'LCU'),
                                                   '--agent', 'codex', '--session', 'direct'])
                account, names = setup.validate(args)
                self.assertEqual((Path(account.pw_dir), names), (home, ['codex']))
                args.session = 'discover'
                with self.assertRaisesRegex(ValueError, 'direct'):
                    setup.validate(args)
                args.session = 'direct'
                args.export = home / 'export'
                with self.assertRaisesRegex(ValueError, 'Windows portable export'):
                    setup.validate(args)

    def test_windows_original_encoded_instruction_tree_copied_byte_exact(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            home = base / 'account'
            home.mkdir()
            release = base / 'release'
            release.mkdir()
            (release / 'installation.json').write_text(json.dumps({'platform': 'windows'}))
            resources = base / 'registered-msix/app/resources'
            modules = resources / 'cua_node/bin/node_modules/%40oai'
            original = b'Original Windows CUA guide \xc3\xa9\r\n'
            paths = [
                modules / 'cua/docs/tinysky-alt-core-cua-repl.md',
                modules / 'cua-repl/instructions/windows/description.md',
                modules / 'sky/docs/skills/oai_sky_lib/windows/SKILL.md',
                modules / 'sky/docs/sky-full-desktop-api.md',
                modules / 'sky/docs/sky-window-api.md',
                modules / 'sky/docs/sky-window2-api.md',
            ]
            for path in paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(original)
            source = Path(__file__).resolve().parents[1] / 'skills/lcu'
            with mock.patch.object(setup, 'installed_app_resources', return_value=resources):
                generated = setup.generate_skill(source, home, release)
            self.assertEqual((generated / 'references/upstream/cua-repl/instructions/windows/description.md').read_bytes(), original)
            self.assertEqual((generated / 'references/upstream/sky/windows/SKILL.md').read_bytes(), original)
            wrapper = (generated / 'SKILL.md').read_text()
            self.assertIn('original Windows computer-use guide', wrapper)
            self.assertNotIn('Chrome browser control', wrapper)
            self.assertFalse((generated / 'references/upstream/chrome').exists())


if __name__ == '__main__':
    unittest.main()
