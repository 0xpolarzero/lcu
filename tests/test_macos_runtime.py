"""The macOS launcher reports metadata from the selected signed app."""
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from lcu.runtime import environment, main, paths


class MacRuntimeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name).resolve()
        self.root = base / 'release'
        self.root.mkdir()
        self.app = base / 'ChatGPT.app'
        self.resources = self.app / 'Contents/Resources'
        self.runtime = self.resources / 'cua_node'
        self.runtime.mkdir(parents=True)
        self.codex = self.resources / 'codex-cli/bin/codex'
        self.code_mode_host = self.resources / 'codex-cli/bin/codex-code-mode-host'
        self.codex.parent.mkdir(parents=True)
        self.codex.write_text('original codex')
        self.code_mode_host.write_text('original host')
        (self.root / 'app').symlink_to(self.app, target_is_directory=True)
        self.policy = {'version': 'old-lock-version', 'runtime': 'old-lock-runtime',
                       'architectures': {'arm64': {'components': {'fixture': 'ignored'}}}}
        (self.root / 'runtime.lock.json').write_text(json.dumps({'platforms': {'darwin': self.policy}}))
        (self.root / 'installation.json').write_text(json.dumps({
            'platform': 'darwin', 'app': str(self.app), 'architecture': 'arm64',
            'package_version': 'old-installed-version', 'runtime': 'old-installed-runtime'}))
        self.selected = SimpleNamespace(
            app=self.app, resources=self.resources, runtime=self.runtime, arch='arm64',
            version='26.924.22138', runtime_version='0.0.24/20260924074400-f52ea85e2a98',
            codex_cli=self.codex, code_mode_host=self.code_mode_host)

    def test_launches_original_entrypoint_with_verified_local_app(self):
        with patch('lcu.platforms.resolve_installed_mac_app', return_value=self.selected) as resolve, \
             patch('lcu.runtime.os.execve') as execute, \
             patch.dict(os.environ, {'HOME': '/fixture'}, clear=True):
            main(self.root, [])
        resolve.assert_called_once_with(self.app, arch='arm64')
        node = self.runtime / 'bin/node'
        self.assertEqual(execute.call_args.args[:2], (node, [str(node), str(
            self.runtime / 'lib/node_modules/@oai/cua-repl/bin/cua-repl.mjs')]))
        env = execute.call_args.args[2]
        self.assertEqual(env['CODEX_CLI_PATH'], str(self.codex))
        self.assertEqual(env['CUA_REPL_ENABLED_SURFACES'], 'computer')
        self.assertEqual(env['SKY_CUA_SERVICE_PATH'], str(
            self.runtime / 'lib/node_modules/@oai/sky/Codex Computer Use.app'))
        self.assertEqual(env['BROWSER_USE_AVAILABLE_BACKENDS'], 'chrome')
        self.assertEqual(env['BROWSER_USE_CODEX_APP_VERSION'], '26.924.22138')
        self.assertNotIn('NODE_REPL_HOST_SERVICES_PIPE_PATH', env)

    def test_reports_current_metadata_after_descriptor_and_lock_become_stale(self):
        with patch('lcu.platforms.resolve_installed_mac_app', return_value=self.selected) as resolve:
            actual = paths(self.root)
        resolve.assert_called_once_with(self.app, arch='arm64')
        self.assertEqual(actual[3], {
            'version': '26.924.22138', 'runtime': '0.0.24/20260924074400-f52ea85e2a98'})
        with patch('lcu.platforms.resolve_installed_mac_app', return_value=self.selected), \
             patch.dict(os.environ, {}, clear=True):
            env = environment(self.root)
        self.assertEqual(env['BROWSER_USE_CODEX_APP_VERSION'], '26.924.22138')

        (self.root / 'bundle.json').write_text(json.dumps({'version': '0.3.0'}))
        output = io.StringIO()
        with patch('lcu.platforms.resolve_installed_mac_app', return_value=self.selected), \
             patch('sys.stdout', output):
            main(self.root, ['--version'])
        self.assertIn('ChatGPT darwin 26.924.22138', output.getvalue())
        self.assertIn('CUA 0.0.24/20260924074400-f52ea85e2a98', output.getvalue())

    def test_rejects_descriptor_pointing_at_a_different_app(self):
        descriptor = self.root / 'installation.json'
        data = json.loads(descriptor.read_text())
        data['app'] = str(self.root / 'other.app')
        descriptor.write_text(json.dumps(data))
        with patch('lcu.platforms.resolve_installed_mac_app') as resolve:
            with self.assertRaisesRegex(ValueError, 'does not match'):
                paths(self.root)
        resolve.assert_not_called()

    def test_source_checkout_version_does_not_advertise_old_lock_values(self):
        (self.root / 'installation.json').unlink()
        output = io.StringIO()
        with patch('sys.stdout', output):
            main(self.root, ['--version'])
        self.assertIn('app not selected', output.getvalue())
        self.assertNotIn('old-lock-version', output.getvalue())

    def test_keeps_caller_helper_and_policy_settings(self):
        with patch('lcu.platforms.resolve_installed_mac_app', return_value=self.selected), \
             patch.dict(os.environ, {'SKY_CUA_SERVICE_PATH': '/chosen/helper.app',
                                     'CUA_REPL_ENABLED_SURFACES': 'computer'}, clear=True):
            env = environment(self.root)
        self.assertEqual(env['SKY_CUA_SERVICE_PATH'], '/chosen/helper.app')
        self.assertEqual(env['CUA_REPL_ENABLED_SURFACES'], 'computer')


if __name__ == '__main__':
    unittest.main()
