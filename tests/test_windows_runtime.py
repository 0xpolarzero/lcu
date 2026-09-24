"""The selected Windows MSIX starts its own CUA server (fixture paths only)."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lcu.runtime import environment, main, paths


class WindowsRuntimeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name).resolve()
        self.root = base / 'release'
        self.root.mkdir()
        self.app = base / 'OpenAI.Codex_26.917.9434.0_x64'
        self.resources = self.app / 'app/resources'
        self.runtime = self.resources / 'cua_node'
        self.launcher = self.runtime / 'bin/node_modules/@oai/cua-repl/bin/cua-repl.mjs'
        self.launcher.parent.mkdir(parents=True)
        self.launcher.write_text('original fixture')
        self.selected = SimpleNamespace(app=self.app, resources=self.resources,
                                        runtime=self.runtime, launcher=self.launcher)
        self.policy = {'version': '26.917.9434.0', 'runtime': 'runtime-fixture',
                       'architectures': {'x64': {'sha256': 'msix-fixture',
                                                  'components': {'fixture': 'digest'}}}}
        (self.root / 'runtime.lock.json').write_text(json.dumps({'platforms': {'windows': self.policy}}))
        (self.root / 'installation.json').write_text(json.dumps({
            'platform': 'windows', 'app': str(self.app), 'architecture': 'x64',
            'package_version': '26.917.9434.0', 'runtime': 'runtime-fixture',
            'sha256': 'msix-fixture'}))

    def test_uses_registered_app_and_original_windows_paths(self):
        with patch('lcu.windows.resolve_installed_windows_app', return_value=self.selected) as resolve:
            selected = paths(self.root)
        self.assertEqual(selected[:3], (self.app, self.resources, self.runtime))
        resolve.assert_called_once_with(expected_version='26.917.9434.0',
            expected_runtime='runtime-fixture', expected_hashes={'fixture': 'digest'})
        with patch.dict(os.environ, {'USERPROFILE': 'C:\\fixture', 'Path': 'C:\\Windows'}, clear=True):
            env = environment(self.root, selected)
        self.assertEqual(env['CODEX_HOME'], 'C:\\fixture\\.codex')
        self.assertEqual(env['NODE_REPL_NODE_PATH'], str(self.runtime / 'bin/node.exe'))
        self.assertEqual(env['CUA_REPL_NODE_REPL_PATH'], str(self.runtime / 'bin/node_repl.exe'))
        self.assertEqual(env['CODEX_CLI_PATH'], str(self.resources / 'codex.exe'))
        self.assertEqual(env['NODE_REPL_NODE_MODULE_DIRS'], str(self.runtime / 'bin/node_modules'))
        self.assertEqual(env['PATH'], str(self.runtime / 'bin') + ';C:\\Windows')
        self.assertEqual(env['BROWSER_USE_CODEX_APP_VERSION'], '26.917.9434.0')

    def test_runs_original_cua_launcher_with_inherited_stdio(self):
        result = subprocess.CompletedProcess([], 0)
        with patch('lcu.windows.resolve_installed_windows_app', return_value=self.selected), \
             patch('lcu.runtime.subprocess.run', return_value=result) as run, \
             patch.dict(os.environ, {'USERPROFILE': 'C:\\fixture'}, clear=True):
            with self.assertRaises(SystemExit) as exit_status:
                main(self.root, [])
        self.assertEqual(exit_status.exception.code, 0)
        self.assertEqual(run.call_args.args[0],
            [str(self.runtime / 'bin/node.exe'), str(self.launcher)])
        self.assertEqual(run.call_args.kwargs['env']['CUA_REPL_ENABLED_SURFACES'], 'computer')
        self.assertNotIn('capture_output', run.call_args.kwargs)

    def test_doctor_uses_windows_sky_without_x11(self):
        with patch('lcu.windows.resolve_installed_windows_app', return_value=self.selected), \
             patch('lcu.runtime.subprocess.run') as run, \
             patch.dict(os.environ, {'USERPROFILE': 'C:\\fixture'}, clear=True):
            main(self.root, ['doctor'])
        self.assertEqual(run.call_args.args[0][0], str(self.runtime / 'bin/node.exe'))
        self.assertEqual(run.call_args.kwargs['cwd'], self.runtime / 'bin')

    def test_refuses_descriptor_for_different_installed_package(self):
        with patch('lcu.windows.resolve_installed_windows_app', return_value=self.selected):
            descriptor = self.root / 'installation.json'
            value = json.loads(descriptor.read_text())
            value['app'] = str(self.root / 'other')
            descriptor.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, 'does not match the registered Windows app'):
                paths(self.root)

    def test_unported_setup_routes_fail_explicitly(self):
        with self.assertRaisesRegex(ValueError, 'Windows agent setup is not implemented'):
            main(self.root, ['setup', '--list-agents'])
        with self.assertRaisesRegex(ValueError, 'Windows browser host setup is not implemented'):
            main(self.root, ['browser', 'install'])

    def test_source_checkout_dispatch_without_installation_descriptor(self):
        (self.root / 'installation.json').unlink()
        with patch('lcu.setup.main') as setup:
            main(self.root, ['setup', '--list-agents'])
        setup.assert_called_once_with(['--list-agents', '--prefix', str(self.root.parent.parent)])
        with patch('lcu.browser.main') as browser:
            main(self.root, ['browser', '--help'])
        browser.assert_called_once_with(self.root, ['--help'])


if __name__ == '__main__':
    unittest.main()
