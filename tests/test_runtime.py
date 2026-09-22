import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lcu.runtime import environment, main
from lcu.browser import install


class UpstreamRuntimeTests(unittest.TestCase):
    def test_default_enables_both_original_surfaces(self):
        with patch.dict(os.environ, {}, clear=True):
            env = environment(Path('/release'))
        self.assertEqual(env['CUA_REPL_ENABLED_SURFACES'], 'browser,computer')
        self.assertEqual(env['CUA_REPL_BROWSER_ENV'], 'codex-app')
        self.assertEqual(env['CODEX_CLI_PATH'], '/release/host/bin/codex')
        self.assertEqual(env['NODE_REPL_NATIVE_PIPE_CONNECT_TIMEOUT_MS'], '1000')
        self.assertEqual(env['BROWSER_USE_TINYSKY_ENABLED'], '1')
        self.assertEqual(env['BROWSER_USE_CODEX_APP_BUILD_FLAVOR'], 'prod')
        self.assertEqual(env['BROWSER_USE_CODEX_APP_VERSION'], '26.915.31945')

    def test_caller_configuration_and_policies_survive(self):
        settings = {'CUA_REPL_BROWSER_ENV': 'orbit', 'CUA_REPL_ENABLED_SURFACES': 'browser',
                    'OAI_SKY_CONFIG_PATH': '/desktop/options.json', 'OAI_SKY_LINUX_BIN': '/engine/sky',
                    'NODE_REPL_JS_BANNER': 'configured startup', 'NODE_REPL_TRUSTED_SERVICES': '{"custom":"service"}',
                    'NODE_REPL_REQUEST_META': '{"test":"context"}', 'NODE_REPL_FORCE_STRICT_AUTO_REVIEW': '1',
                    'NODE_REPL_ENFORCE_MODEL_CHECK': '1', 'CODEX_CLI_PATH': '/host/codex',
                    'BROWSER_USE_AVAILABLE_BACKENDS': 'chrome,cdp,iab', 'BROWSER_USE_CONFIG_PATH': '/browser.json',
                    'NODE_REPL_ENABLE_NETWORK_ISOLATION': '1', 'NODE_REPL_DISABLE_ANALYTICS': '0',
                    'BROWSER_USE_TINYSKY_ENABLED': '0', 'NODE_REPL_NATIVE_PIPE_CONNECT_TIMEOUT_MS': '2300',
                    'BROWSER_USE_CODEX_APP_BUILD_FLAVOR': 'alpha', 'BROWSER_USE_CODEX_APP_VERSION': 'fixture'}
        with patch.dict(os.environ, settings, clear=True):
            env = environment(Path('/release'))
        for key, value in settings.items():
            self.assertEqual(env[key], value, key)

    def test_generic_connection_identity_has_no_invented_policy_or_model(self):
        with patch.dict(os.environ, {}, clear=True):
            first = environment(Path('/release'))
            second = environment(Path('/release'))
        metadata = json.loads(first['NODE_REPL_REQUEST_META'])
        self.assertEqual(set(metadata), {'x-codex-turn-metadata'})
        turn = metadata['x-codex-turn-metadata']
        self.assertEqual(set(turn), {'session_id', 'turn_id'})
        self.assertNotEqual(first['NODE_REPL_REQUEST_META'], second['NODE_REPL_REQUEST_META'])

    def test_additional_module_and_trust_roots_survive(self):
        settings = {'NODE_REPL_NODE_MODULE_DIRS': '/extra/modules',
                    'NODE_REPL_TRUSTED_CODE_PATHS': '/trusted', 'PATH': '/usr/bin'}
        with patch.dict(os.environ, settings, clear=True):
            env = environment(Path('/release'))
        self.assertEqual(env['NODE_REPL_NODE_MODULE_DIRS'], '/release/runtime/lib/node_modules:/extra/modules')
        self.assertEqual(env['NODE_REPL_TRUSTED_CODE_PATHS'],
                         '/release/runtime/lib/node_modules:/release/host/plugins:/trusted')

    def test_launches_original_entrypoint(self):
        with patch.dict(os.environ, {'CUA_REPL_ENABLED_SURFACES': 'computer'}), patch('lcu.runtime.os.execve') as execute:
            main(Path('/release'), [])
        self.assertEqual(execute.call_args.args[1],
            ['/release/runtime/bin/node', '/release/runtime/lib/node_modules/@oai/cua-repl/bin/cua-repl.mjs'])

    def test_explicit_original_browser_host_owns_its_mcp_connection(self):
        with patch.dict(os.environ, {}, clear=True), patch('lcu.host_bridge.run_mcp', return_value=0) as serve:
            main(Path('/release'), ['--with-browser-host'])
        self.assertEqual(serve.call_args.args[2],
            ['/release/runtime/bin/node', '/release/runtime/lib/node_modules/@oai/cua-repl/bin/cua-repl.mjs'])

    def test_default_combined_runtime_does_not_require_an_electron_host(self):
        with patch.dict(os.environ, {}, clear=True), patch('lcu.runtime.os.execve') as execute:
            main(Path('/release'), [])
        self.assertEqual(execute.call_args.args[2]['CUA_REPL_ENABLED_SURFACES'], 'browser,computer')

    def test_browser_setup_refuses_foreign_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            plugin = root / 'host/plugins/chrome/scripts'
            plugin.mkdir(parents=True)
            (plugin / 'installManifest.mjs').write_text('upstream fixture')
            foreign = root / 'foreign'
            foreign.mkdir()
            (foreign / 'keep').write_text('existing data')
            with self.assertRaisesRegex(ValueError, 'another installation'):
                install(root, foreign)
            self.assertEqual((foreign / 'keep').read_text(), 'existing data')


if __name__ == '__main__':
    unittest.main()
