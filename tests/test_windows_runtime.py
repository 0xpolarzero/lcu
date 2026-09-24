"""The managed private Windows app starts its original CUA server."""

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
        prefix = base / 'prefix'
        self.root = prefix / 'releases/release'
        self.root.mkdir(parents=True)
        self.app = prefix / 'apps/msix-fixture/app'
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

    def test_uses_managed_app_and_original_windows_paths(self):
        with patch('lcu.windows.validate_windows_app_tree', return_value=self.selected) as resolve:
            selected = paths(self.root)
        self.assertEqual(selected[:3], (self.app, self.resources, self.runtime))
        resolve.assert_called_once_with(self.app, expected_version='26.917.9434.0',
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
        with patch('lcu.windows.validate_windows_app_tree', return_value=self.selected), \
             patch('lcu.windows_host.start_original_host', return_value=(
                 'host', '\\\\.\\pipe\\lcu-wre-fixture', '\\\\.\\pipe\\lcu-lifetime-fixture')) as start, \
             patch('lcu.windows_host.stop_original_host') as stop, \
             patch('lcu.runtime.subprocess.run', return_value=result) as run, \
             patch.dict(os.environ, {'USERPROFILE': 'C:\\fixture'}, clear=True):
            with self.assertRaises(SystemExit) as exit_status:
                main(self.root, [])
        self.assertEqual(exit_status.exception.code, 0)
        self.assertEqual(run.call_args.args[0],
            [str(self.runtime / 'bin/node.exe'), str(self.launcher)])
        self.assertEqual(run.call_args.kwargs['env']['CUA_REPL_ENABLED_SURFACES'], 'computer')
        self.assertEqual(run.call_args.kwargs['env']['SKY_CUA_NATIVE_PIPE'], '1')
        self.assertEqual(run.call_args.kwargs['env']['SKY_CUA_NATIVE_PIPE_DIRECTORY'], '\\\\.\\pipe\\lcu-wre-fixture')
        self.assertEqual(run.call_args.kwargs['env']['LCU_WRE_LIFETIME_PIPE'], '\\\\.\\pipe\\lcu-lifetime-fixture')
        self.assertEqual(json.loads(run.call_args.kwargs['env']['NODE_REPL_TRUSTED_SERVICES'])['sky'],
                         str(self.root / 'lcu-host/windows-sky-service.mjs'))
        self.assertNotIn('capture_output', run.call_args.kwargs)
        self.assertEqual(start.call_args.kwargs['entry'], self.root / 'lcu-host/windows-pipe-host.cjs')
        stop.assert_called_once_with('host')

    def test_doctor_uses_windows_sky_without_x11(self):
        with patch('lcu.windows.validate_windows_app_tree', return_value=self.selected), \
             patch('lcu.runtime.subprocess.run') as run, \
             patch.dict(os.environ, {'USERPROFILE': 'C:\\fixture'}, clear=True):
            main(self.root, ['doctor'])
        self.assertEqual(run.call_args.args[0][0], str(self.runtime / 'bin/node.exe'))
        self.assertEqual(run.call_args.kwargs['cwd'], self.runtime / 'bin')

    def test_disposes_owned_host_when_original_mcp_fails(self):
        with patch('lcu.windows.validate_windows_app_tree', return_value=self.selected), \
             patch('lcu.windows_host.start_original_host', return_value=(
                 'owned-host', '\\\\.\\pipe\\lcu-wre-fixture', '\\\\.\\pipe\\lcu-lifetime-fixture')), \
             patch('lcu.windows_host.stop_original_host') as stop, \
             patch('lcu.runtime.subprocess.run', side_effect=OSError('MCP failed')), \
             patch.dict(os.environ, {'USERPROFILE': 'C:\\fixture'}, clear=True):
            with self.assertRaisesRegex(OSError, 'MCP failed'):
                main(self.root, [])
        stop.assert_called_once_with('owned-host')

    def test_preserves_other_trusted_services_and_rejects_custom_sky(self):
        ready = ('owned-host', '\\\\.\\pipe\\lcu-wre-fixture',
                 '\\\\.\\pipe\\lcu-lifetime-fixture')
        with patch('lcu.windows.validate_windows_app_tree', return_value=self.selected), \
             patch('lcu.windows_host.start_original_host', return_value=ready), \
             patch('lcu.windows_host.stop_original_host') as stop, \
             patch('lcu.runtime.subprocess.run', return_value=subprocess.CompletedProcess([], 0)) as run, \
             patch.dict(os.environ, {'USERPROFILE': 'C:\\fixture',
                                     'NODE_REPL_TRUSTED_SERVICES': '{"browser":"fixture"}'}, clear=True):
            with self.assertRaises(SystemExit):
                main(self.root, [])
        self.assertEqual(json.loads(run.call_args.kwargs['env']['NODE_REPL_TRUSTED_SERVICES'])['browser'],
                         'fixture')
        with patch('lcu.windows.validate_windows_app_tree', return_value=self.selected), \
             patch('lcu.windows_host.start_original_host', return_value=ready), \
             patch('lcu.windows_host.stop_original_host') as stop, \
             patch('lcu.runtime.subprocess.run') as run, \
             patch.dict(os.environ, {'USERPROFILE': 'C:\\fixture',
                                     'NODE_REPL_TRUSTED_SERVICES': '{"sky":"custom"}'}, clear=True):
            with self.assertRaisesRegex(ValueError, 'conflicts'):
                main(self.root, [])
        run.assert_not_called()
        stop.assert_called_once_with('owned-host')
        with patch('lcu.windows.validate_windows_app_tree', return_value=self.selected), \
             patch('lcu.windows_host.start_original_host', return_value=ready), \
             patch('lcu.windows_host.stop_original_host') as stop, \
             patch('lcu.runtime.subprocess.run') as run, \
             patch.dict(os.environ, {'USERPROFILE': 'C:\\fixture',
                                     'NODE_REPL_TRUSTED_SERVICES': 'null'}, clear=True):
            with self.assertRaisesRegex(ValueError, 'JSON string map'):
                main(self.root, [])
        run.assert_not_called()
        stop.assert_called_once_with('owned-host')

    def test_chrome_keeps_original_browser_trusted_service(self):
        ready = ('owned-host', '\\\\.\\pipe\\lcu-wre-fixture',
                 '\\\\.\\pipe\\lcu-lifetime-fixture')
        with patch('lcu.windows.validate_windows_app_tree', return_value=self.selected), \
             patch('lcu.windows_host.start_original_host', return_value=ready), \
             patch('lcu.windows_host.stop_original_host'), \
             patch('lcu.runtime.subprocess.run', return_value=subprocess.CompletedProcess([], 0)) as run, \
             patch.dict(os.environ, {'USERPROFILE': 'C:\\fixture'}, clear=True):
            with self.assertRaises(SystemExit):
                main(self.root, ['--chrome'])
        services = json.loads(run.call_args.kwargs['env']['NODE_REPL_TRUSTED_SERVICES'])
        self.assertEqual(services['browser'], '@oai/browser-desktop/service')
        self.assertEqual(services['sky'], str(self.root / 'lcu-host/windows-sky-service.mjs'))
        with patch('lcu.windows.validate_windows_app_tree', return_value=self.selected), \
             patch('lcu.windows_host.start_original_host', return_value=ready), \
             patch('lcu.windows_host.stop_original_host'), \
             patch('lcu.runtime.subprocess.run', return_value=subprocess.CompletedProcess([], 0)) as run, \
             patch.dict(os.environ, {'USERPROFILE': 'C:\\fixture',
                                     'NODE_REPL_TRUSTED_SERVICES': '{"fixture":"service"}'}, clear=True):
            with self.assertRaises(SystemExit):
                main(self.root, ['--chrome'])
        services = json.loads(run.call_args.kwargs['env']['NODE_REPL_TRUSTED_SERVICES'])
        self.assertNotIn('browser', services)
        self.assertEqual(services['fixture'], 'service')

    def test_refuses_descriptor_for_different_installed_package(self):
        with patch('lcu.windows.validate_windows_app_tree', return_value=self.selected):
            descriptor = self.root / 'installation.json'
            value = json.loads(descriptor.read_text())
            value['app'] = str(self.root / 'other')
            descriptor.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, 'not the managed private generation'):
                paths(self.root)

    def test_setup_and_browser_dispatch(self):
        with patch('lcu.setup.main') as setup:
            main(self.root, ['setup', '--list-agents'])
        setup.assert_called_once_with(['--list-agents', '--prefix', str(self.root.parent.parent)])
        with patch('lcu.browser.main') as browser:
            main(self.root, ['browser', 'install'])
        browser.assert_called_once_with(self.root, ['install'])

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
