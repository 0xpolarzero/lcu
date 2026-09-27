"""The macOS launcher reports metadata from the selected signed app."""
import io
import json
import os
from pathlib import Path
import socket
import sys
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
             patch('lcu.runtime._configure_macos_lifecycle', return_value=None), \
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

    def test_macos_main_supervises_lifecycle_host_around_original_repl(self):
        from lcu import macos_host
        client = self.runtime / 'lib/node_modules/@oai/sky/Codex Computer Use.app/Contents/SharedSupport/SkyComputerUseClient.app/Contents/MacOS/SkyComputerUseClient'
        client.parent.mkdir(parents=True)
        client.write_text('fixture')
        client.chmod(0o755)
        host = object()
        temporary = object()
        with patch('lcu.platforms.resolve_installed_mac_app', return_value=self.selected), \
             patch('lcu.macos_host.start_original_host', return_value=(host, temporary, '/tmp/lcu.sock')) as start, \
             patch('lcu.macos_host.stop_original_host') as stop, \
             patch('lcu.runtime.subprocess.run', return_value=SimpleNamespace(returncode=0)) as run, \
             patch.dict(os.environ, {'HOME': '/fixture'}, clear=True):
            with self.assertRaises(SystemExit) as result:
                main(self.root, [])
        self.assertEqual(result.exception.code, 0)
        start.assert_called_once()
        stop.assert_called_once_with(host, temporary)
        self.assertEqual(run.call_args.args[0], [str(self.runtime / 'bin/node'), str(
            self.runtime / 'lib/node_modules/@oai/cua-repl/bin/cua-repl.mjs')])
        self.assertEqual(run.call_args.kwargs['env']['LCU_MAC_LIFETIME_SOCKET'], '/tmp/lcu.sock')
        self.assertEqual(json.loads(run.call_args.kwargs['env']['NODE_REPL_TRUSTED_SERVICES'])['sky'],
                         str(self.root / 'lcu/macos_sky_service.mjs'))

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

    def test_configures_original_sky_service_lifecycle_wrapper(self):
        from lcu.runtime import _configure_macos_lifecycle
        wrapper = self.root / 'lcu/macos_sky_service.mjs'
        with patch.dict(os.environ, {'HOME': '/fixture', 'NODE_REPL_TRUSTED_SERVICES': json.dumps({
                'sky': '@oai/sky/service', 'browser': 'custom/browser/service',
                'other': 'custom/other/service'})}, clear=True):
            env = environment(self.root, (self.app, self.resources, self.runtime, {
                'version': '26.924.22138', 'runtime': 'fixture'}))
            client = _configure_macos_lifecycle(self.root, self.runtime, env)
        services = json.loads(env['NODE_REPL_TRUSTED_SERVICES'])
        self.assertEqual(services, {
            'sky': str(wrapper), 'browser': 'custom/browser/service',
            'other': 'custom/other/service'})
        self.assertEqual(env['LCU_MAC_SKY_SERVICE_PATH'], str(
            self.runtime / 'lib/node_modules/@oai/sky/dist/project/cua/sky_js/src/service.js'))
        self.assertEqual(client, Path(env['SKY_CUA_SERVICE_PATH']) /
            'Contents/SharedSupport/SkyComputerUseClient.app/Contents/MacOS/SkyComputerUseClient')

    def test_rejects_custom_sky_trusted_service_when_cleanup_wrapper_is_required(self):
        from lcu.runtime import _configure_macos_lifecycle
        env = {'CUA_REPL_ENABLED_SURFACES': 'computer',
               'NODE_REPL_TRUSTED_SERVICES': json.dumps({'sky': 'custom/sky/service'})}
        with self.assertRaisesRegex(ValueError, 'custom Sky trusted-service'):
            _configure_macos_lifecycle(self.root, self.runtime, env)

    def test_lifecycle_host_passes_ids_to_fake_original_client(self):
        from lcu.macos_host import start_original_host, stop_original_host
        capture = self.root / 'client-argv.json'
        client = self.root / 'fake-client'
        client.write_text('#!/usr/bin/env python3\nimport json,sys\n'
                          f'open({str(capture)!r}, "w").write(json.dumps(sys.argv[1:]))\n')
        client.chmod(0o755)
        process, temporary, address = start_original_host(
            python=Path(sys.executable), client=client,
            entry=Path(__file__).resolve().parents[1] / 'lcu/macos_host.py', env=os.environ.copy())
        try:
            def request(raw):
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                    connection.settimeout(4)
                    connection.connect(address)
                    connection.sendall(raw)
                    response = bytearray()
                    while b'\n' not in response:
                        response.extend(connection.recv(1024))
                    return json.loads(response)

            malformed = request(b'{"session_id":"","turn_id":"turn-exact"}\n')
            self.assertFalse(malformed['notified'])
            self.assertIn('turn IDs are missing', malformed['error'])
            self.assertEqual(request(
                b'{"session_id":"session-exact","turn_id":"turn-exact"}\n'), {'notified': True})
            argv = json.loads(capture.read_text())
            self.assertEqual(argv[0], 'turn-ended')
            self.assertEqual(json.loads(argv[1]), {
                'type': 'agent-turn-complete',
                'thread-id': 'session-exact', 'turn-id': 'turn-exact'})
        finally:
            stop_original_host(process, temporary)

    def test_lifecycle_host_reports_original_client_failure(self):
        from lcu.macos_host import start_original_host, stop_original_host
        client = self.root / 'failing-client'
        client.write_text('#!/usr/bin/env python3\nraise SystemExit(23)\n')
        client.chmod(0o755)
        process, temporary, address = start_original_host(
            python=Path(sys.executable), client=client,
            entry=Path(__file__).resolve().parents[1] / 'lcu/macos_host.py', env=os.environ.copy())
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(4)
                connection.connect(address)
                connection.sendall(b'{"session_id":"session","turn_id":"turn"}\n')
                response = bytearray()
                while b'\n' not in response:
                    response.extend(connection.recv(1024))
            result = json.loads(response)
            self.assertFalse(result['notified'])
            self.assertIn('status 23', result['error'])
        finally:
            stop_original_host(process, temporary)


if __name__ == '__main__':
    unittest.main()
