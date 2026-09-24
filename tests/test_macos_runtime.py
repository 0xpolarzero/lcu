"""The macOS launch path still executes the original persistent CUA server."""
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
        (self.root / 'app').symlink_to(self.app, target_is_directory=True)
        self.policy = {'version': 'mac-fixture', 'runtime': 'runtime-fixture',
                       'architectures': {'arm64': {'components': {'fixture': 'digest'}}}}
        (self.root / 'runtime.lock.json').write_text(json.dumps({'platforms': {'darwin': self.policy}}))
        (self.root / 'installation.json').write_text(json.dumps({
            'platform': 'darwin', 'app': str(self.app), 'architecture': 'arm64',
            'package_version': 'mac-fixture', 'runtime': 'runtime-fixture'}))
        self.selected = SimpleNamespace(app=self.app, resources=self.resources,
                                        runtime=self.runtime, arch='arm64')

    def test_launches_original_entrypoint_with_verified_local_app(self):
        with patch('lcu.platforms.resolve_installed_mac_app', return_value=self.selected) as resolve, \
             patch('lcu.runtime.os.execve') as execute, \
             patch.dict(os.environ, {'HOME': '/fixture'}, clear=True):
            main(self.root, [])
        resolve.assert_called_once_with(self.app, expected_version='mac-fixture',
                                        expected_runtime='runtime-fixture',
                                        expected_hashes={'fixture': 'digest'}, arch='arm64')
        node = self.runtime / 'bin/node'
        self.assertEqual(execute.call_args.args[:2], (node, [str(node), str(
            self.runtime / 'lib/node_modules/@oai/cua-repl/bin/cua-repl.mjs')]))
        env = execute.call_args.args[2]
        self.assertEqual(env['CUA_REPL_ENABLED_SURFACES'], 'computer')
        self.assertEqual(env['SKY_CUA_SERVICE_PATH'], str(
            self.runtime / 'lib/node_modules/@oai/sky/Codex Computer Use.app'))
        self.assertEqual(env['BROWSER_USE_AVAILABLE_BACKENDS'], 'chrome')
        self.assertNotIn('NODE_REPL_HOST_SERVICES_PIPE_PATH', env)

    def test_rejects_changed_app_identity_before_launch(self):
        descriptor = self.root / 'installation.json'
        data = json.loads(descriptor.read_text())
        data['package_version'] = 'another-version'
        descriptor.write_text(json.dumps(data))
        with patch('lcu.platforms.resolve_installed_mac_app') as resolve:
            with self.assertRaisesRegex(ValueError, 'does not match'):
                paths(self.root)
        resolve.assert_not_called()

    def test_keeps_caller_helper_and_policy_settings(self):
        with patch('lcu.platforms.resolve_installed_mac_app', return_value=self.selected), \
             patch.dict(os.environ, {'SKY_CUA_SERVICE_PATH': '/chosen/helper.app',
                                     'CUA_REPL_ENABLED_SURFACES': 'computer'}, clear=True):
            env = environment(self.root)
        self.assertEqual(env['SKY_CUA_SERVICE_PATH'], '/chosen/helper.app')
        self.assertEqual(env['CUA_REPL_ENABLED_SURFACES'], 'computer')


if __name__ == '__main__':
    unittest.main()
