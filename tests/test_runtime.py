import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lcu.runtime import environment, main
from lcu.browser import install


class UpstreamRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        resources = self.root / 'app/resources'
        runtime = resources / 'cua_node'
        for relative in (
            'bin/node', 'bin/node_repl',
            'lib/node_modules/@oai/cua-repl/bin/cua-repl.mjs',
        ):
            path = runtime / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('fixture')
            path.chmod(0o755)
        for relative in (
            'codex', 'codex-code-mode-host',
            'plugins/openai-bundled/plugins/chrome/.codex-plugin/plugin.json',
            'plugins/openai-bundled/plugins/unified-computer-use/.mcp.json',
        ):
            path = resources / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('fixture')
            path.chmod(0o755)
        (runtime / 'manifest.json').write_text(json.dumps({
            'platform': 'linux', 'arch': 'arm64', 'runtime_archive_version': 'fixture-runtime',
        }))
        (self.root / 'runtime.lock.json').write_text(json.dumps({
            'runtime': 'fixture-runtime', 'version': '26.915.31945',
            'architectures': {'arm64': {'sha256': 'fixture-digest'}},
        }))
        (self.root / 'installation.json').write_text(json.dumps({
            'app': 'app', 'architecture': 'arm64', 'package_version': '26.915.31945',
            'sha256': 'fixture-digest',
        }))

    def tearDown(self):
        self.temporary.cleanup()

    def test_default_enables_both_original_surfaces(self):
        with patch.dict(os.environ, {}, clear=True):
            env = environment(self.root)
        self.assertEqual(env['CUA_REPL_ENABLED_SURFACES'], 'browser,computer')
        self.assertEqual(env['CUA_REPL_BROWSER_ENV'], 'codex-app')
        self.assertEqual(env['CODEX_CLI_PATH'], str(self.root / 'app/resources/codex'))
        self.assertEqual(env['BROWSER_USE_AVAILABLE_BACKENDS'], 'chrome')
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
            env = environment(self.root)
        for key, value in settings.items():
            self.assertEqual(env[key], value, key)

    def test_generic_connection_identity_has_no_invented_policy_or_model(self):
        with patch.dict(os.environ, {}, clear=True):
            first = environment(self.root)
            second = environment(self.root)
        metadata = json.loads(first['NODE_REPL_REQUEST_META'])
        self.assertEqual(set(metadata), {'x-codex-turn-metadata'})
        turn = metadata['x-codex-turn-metadata']
        self.assertEqual(set(turn), {'session_id', 'turn_id'})
        self.assertNotEqual(first['NODE_REPL_REQUEST_META'], second['NODE_REPL_REQUEST_META'])

    def test_additional_module_and_trust_roots_survive(self):
        settings = {'NODE_REPL_NODE_MODULE_DIRS': '/extra/modules',
                    'NODE_REPL_TRUSTED_CODE_PATHS': '/trusted', 'PATH': '/usr/bin'}
        with patch.dict(os.environ, settings, clear=True), patch('lcu.runtime.Path.home', return_value=Path('/fixture')):
            env = environment(self.root)
        modules = self.root / 'app/resources/cua_node/lib/node_modules'
        plugins = self.root / 'app/resources/plugins'
        self.assertEqual(env['NODE_REPL_NODE_MODULE_DIRS'], f'{modules}:/extra/modules')
        self.assertEqual(env['NODE_REPL_TRUSTED_CODE_PATHS'],
                         f'/fixture/.codex:{modules}:{plugins}:/trusted')

    def test_default_codex_home_is_supplied_and_trusted(self):
        with patch.dict(os.environ, {}, clear=True), patch('lcu.runtime.Path.home', return_value=Path('/fixture')):
            env = environment(self.root)
        self.assertEqual(env['CODEX_HOME'], '/fixture/.codex')
        self.assertEqual(env['NODE_REPL_TRUSTED_CODE_PATHS'].split(os.pathsep)[0], '/fixture/.codex')

    def test_default_home_matches_node_posix_join(self):
        for home, expected in (('', '.codex'), ('relative/home', 'relative/home/.codex'),
                               ('relative/../home', 'home/.codex'), ('//fixture/home', '/fixture/home/.codex')):
            with self.subTest(home=home), patch.dict(os.environ, {'HOME': home}, clear=True):
                env = environment(self.root)
                self.assertEqual(env['CODEX_HOME'], expected)
                self.assertEqual(env['NODE_REPL_TRUSTED_CODE_PATHS'].split(os.pathsep)[0], expected)

    def test_explicit_codex_home_is_not_normalized(self):
        for selected in ('/fixture/custom', 'relative/../home', '  /fixture/spaces  ', ''):
            with self.subTest(selected=selected), patch.dict(os.environ, {'CODEX_HOME': selected}, clear=True):
                env = environment(self.root)
                self.assertEqual(env['CODEX_HOME'], selected)
                modules = self.root / 'app/resources/cua_node/lib/node_modules'
                plugins = self.root / 'app/resources/plugins'
                self.assertEqual(env['NODE_REPL_TRUSTED_CODE_PATHS'],
                                 (selected + ':' if selected else '') +
                                 f'{modules}:{plugins}')

    def test_launches_original_entrypoint(self):
        with patch.dict(os.environ, {'CUA_REPL_ENABLED_SURFACES': 'computer'}), patch('lcu.runtime.os.execve') as execute:
            main(self.root, [])
        self.assertEqual(execute.call_args.args[1],
            [str(self.root / 'app/resources/cua_node/bin/node'),
             str(self.root / 'app/resources/cua_node/lib/node_modules/@oai/cua-repl/bin/cua-repl.mjs')])

    def test_mcp_discovery_compat_probes_then_execs_original_server(self):
        following = b'{"jsonrpc":"2.0","id":1,"method":"initialize"}\n'
        source = io.BytesIO(b'{"jsonrpc":"2.0","id":0,"method":"server/discover"}\n' + following)
        destination = io.BytesIO()
        stdin = SimpleNamespace(buffer=SimpleNamespace(raw=source))
        stdout = SimpleNamespace(buffer=destination)
        with patch('lcu.runtime.sys.stdin', stdin), patch('lcu.runtime.sys.stdout', stdout), \
                patch('lcu.runtime.os.execve') as execute:
            main(self.root, ['--mcp-discovery-compat'])

        self.assertEqual(json.loads(destination.getvalue()), {
            'jsonrpc': '2.0', 'id': 0,
            'error': {'code': -32601, 'message': 'Method not found'},
        })
        self.assertEqual(source.read(), following)
        node = self.root / 'app/resources/cua_node/bin/node'
        launcher = self.root / 'app/resources/cua_node/lib/node_modules/@oai/cua-repl/bin/cua-repl.mjs'
        execute.assert_called_once()
        self.assertEqual(execute.call_args.args[:2], (node, [str(node), str(launcher)]))

    def test_mcp_discovery_compat_rejects_other_first_request_without_launching(self):
        source = io.BytesIO(b'{"jsonrpc":"2.0","id":0,"method":"tools/list"}\n')
        destination = io.BytesIO()
        stdin = SimpleNamespace(buffer=SimpleNamespace(raw=source))
        stdout = SimpleNamespace(buffer=destination)
        with patch('lcu.runtime.sys.stdin', stdin), patch('lcu.runtime.sys.stdout', stdout), \
                patch('lcu.runtime.os.execve') as execute:
            with self.assertRaisesRegex(ValueError, 'initial JSON-RPC server/discover request'):
                main(self.root, ['--mcp-discovery-compat'])
        execute.assert_not_called()
        self.assertEqual(destination.getvalue(), b'')

    def test_retargeted_app_link_is_rejected_before_launch(self):
        descriptor = self.root / 'installation.json'
        data = json.loads(descriptor.read_text())
        data['app'] = 'another-generation'
        descriptor.write_text(json.dumps(data))
        with patch('lcu.runtime.os.execve') as execute:
            with self.assertRaisesRegex(ValueError, 'descriptor does not match'):
                main(self.root, [])
        execute.assert_not_called()

    def test_removed_embedded_browser_flag_has_migration_error(self):
        with self.assertRaisesRegex(ValueError, 'lcu browser install'):
            main(self.root, ['--with-browser-host'])

    def test_default_combined_runtime_does_not_require_an_electron_host(self):
        with patch.dict(os.environ, {}, clear=True), patch('lcu.runtime.os.execve') as execute:
            main(self.root, [])
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
