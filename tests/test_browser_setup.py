"""Native-host setup tests use only disposable homes and a fake upstream installer."""
import json
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lcu.browser import _manifest_paths, install, status


class BrowserSetupTests(unittest.TestCase):
    def test_macos_manifest_locations_match_original_installer(self):
        home = Path('/private/tmp/disposable-home')
        paths = _manifest_paths({'HOME': str(home)}, 'Darwin')
        self.assertEqual(len(paths), 8)
        self.assertIn(home / 'Library/Application Support/Google/Chrome/NativeMessagingHosts/com.openai.codexextension.json', paths)
        self.assertIn(home / 'Library/Application Support/Microsoft Edge/NativeMessagingHosts/com.openai.codexextension.json', paths)
        self.assertIn(home / 'Library/Application Support/BraveSoftware/Brave-Browser/NativeMessagingHosts/com.openai.codexextension.json', paths)

    def test_macos_setup_rewrites_only_manifests_for_selected_original_host(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / 'release'
            home = base / 'home'
            resources = root / 'app/Contents/Resources'
            source = resources / 'plugins/openai-bundled/plugins/chrome'
            (source / 'scripts').mkdir(parents=True)
            (source / 'scripts/installManifest.mjs').write_text('fixture')
            host = source / 'extension-host/macos/arm64/ChatGPT for Chrome'
            host.parent.mkdir(parents=True)
            host.write_text('fixture')
            relay_source = root / 'lcu/native_host.py'
            relay_source.parent.mkdir(parents=True)
            relay_source.write_text('#!/usr/bin/env python3\n')
            home.mkdir()
            env = {'HOME': str(home), 'NODE_REPL_NODE_PATH': '/fake/node',
                   'CODEX_CLI_PATH': '/fake/codex', 'CUA_REPL_NODE_REPL_PATH': '/fake/repl'}
            chrome_manifest = home / 'Library/Application Support/Google/Chrome/NativeMessagingHosts/com.openai.codexextension.json'
            edge_manifest = home / 'Library/Application Support/Microsoft Edge/NativeMessagingHosts/com.openai.codexextension.json'
            unrelated = home / 'Library/Application Support/BraveSoftware/Brave-Browser/NativeMessagingHosts/com.openai.codexextension.json'

            def original_installer(*args, **kwargs):
                destination = home / 'Library/Application Support/lcu/browser'
                plugin = next(destination.iterdir()) / 'chrome'
                selected_host = str(plugin / 'extension-host/macos/arm64/ChatGPT for Chrome')
                for path, selected in ((chrome_manifest, selected_host),
                                       (edge_manifest, selected_host),
                                       (unrelated, '/other/ChatGPT for Chrome')):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps({'name': 'com.openai.codexextension',
                                                'path': selected, 'allowed_origins': ['chrome-extension://fixture/']}))

            with mock.patch('lcu.browser.platform.system', return_value='Darwin'), \
                    mock.patch.dict(os.environ, {'HOME': str(home)}), \
                    mock.patch('lcu.runtime.paths', return_value=(root / 'app', resources, None, {})), \
                    mock.patch('lcu.runtime.environment', return_value=env), \
                    mock.patch('lcu.browser.subprocess.run', side_effect=original_installer) as run:
                destination = install(root)

            expected_relay = destination / 'lcu-native-host'
            self.assertEqual(json.loads(chrome_manifest.read_text())['path'], str(expected_relay))
            self.assertEqual(json.loads(edge_manifest.read_text())['path'], str(expected_relay))
            self.assertEqual(json.loads(unrelated.read_text())['path'], '/other/ChatGPT for Chrome')
            self.assertEqual(json.loads(chrome_manifest.read_text())['allowed_origins'],
                             ['chrome-extension://fixture/'])
            self.assertEqual((destination / '.lcu-browser-host').read_text(), str((root / 'app').resolve()) + '\n')
            self.assertEqual(expected_relay.stat().st_mode & 0o777, 0o700)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0][0], '/fake/node')
            self.assertTrue((destination / 'chrome/scripts/installManifest.mjs').is_file())

    def test_macos_missing_original_manifest_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / 'release'
            resources = root / 'app/Contents/Resources'
            source = resources / 'plugins/openai-bundled/plugins/chrome/scripts'
            source.mkdir(parents=True)
            (source / 'installManifest.mjs').write_text('fixture')
            relay_source = root / 'lcu/native_host.py'
            relay_source.parent.mkdir(parents=True)
            relay_source.write_text('fixture')
            home = base / 'home'
            home.mkdir()
            env = {'HOME': str(home), 'NODE_REPL_NODE_PATH': '/fake/node',
                   'CODEX_CLI_PATH': '/fake/codex', 'CUA_REPL_NODE_REPL_PATH': '/fake/repl'}
            with mock.patch('lcu.browser.platform.system', return_value='Darwin'), \
                    mock.patch.dict(os.environ, {'HOME': str(home)}), \
                    mock.patch('lcu.runtime.paths', return_value=(root / 'app', resources, None, {})), \
                    mock.patch('lcu.runtime.environment', return_value=env), \
                    mock.patch('lcu.browser.subprocess.run'):
                with self.assertRaisesRegex(ValueError, 'produced no manifest'):
                    install(root)


class BrowserStatusTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        resources = self.root / 'app/Contents/Resources'
        scripts = resources / 'plugins/openai-bundled/plugins/chrome/scripts'
        scripts.mkdir(parents=True)
        (scripts / 'extension-ids.json').write_text(json.dumps({'browserDiagnostics': [{
            'browserFamily': 'chrome', 'shortDisplayName': 'Chrome',
            'extensionManagementUrl': 'chrome://extensions', 'storeUrl': 'https://official.example/extension'}]}))
        self.host_dir = self.root / 'private-host'
        self.host_dir.mkdir()
        (self.host_dir / '.lcu-browser-host').write_text(str((self.root / 'app').resolve()) + '\n')
        self.relay = self.host_dir / 'lcu-native-host'
        self.relay.write_text('fixture relay')
        self.relay.chmod(0o700)
        source = self.root / 'lcu/native_host.py'
        source.parent.mkdir()
        source.write_bytes(self.relay.read_bytes())
        host = self.host_dir / 'chrome/extension-host/macos/arm64/ChatGPT for Chrome'
        host.parent.mkdir(parents=True)
        host.write_text('fixture host')
        host.chmod(0o700)
        self.manifest = self.root / 'manifest.json'
        self.manifest.write_text(json.dumps({'path': str(self.relay)}))
        self.extension = {'enabled': True, 'installed': True, 'selectedProfileDirectory': 'Default'}
        self.output = io.StringIO()
        patches = [
            mock.patch('lcu.runtime.paths', return_value=(None, resources, None, {})),
            mock.patch('lcu.runtime.environment', return_value={'NODE_REPL_NODE_PATH': '/original/node'}),
            mock.patch('lcu.browser.platform.system', return_value='Darwin'),
            mock.patch('lcu.browser.platform.machine', return_value='arm64'),
            mock.patch('sys.stdout', self.output),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def run_status(self):
        results = [mock.Mock(stdout=json.dumps(self.extension)),
                   mock.Mock(stdout=json.dumps({'correct': True, 'manifestPath': str(self.manifest)}))]
        with mock.patch('lcu.browser.subprocess.run', side_effect=results):
            return status(self.root)

    def test_valid_setup_does_not_claim_live_connection_or_write_files(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertTrue(self.run_status())
        self.assertIn('Live browser connection: not checked', self.output.getvalue())
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_enabled_extension_with_original_host_is_not_lcu_ready(self):
        self.manifest.write_text(json.dumps({'path': '/original/ChatGPT for Chrome'}))
        self.assertFalse(self.run_status())
        self.assertIn('lcu browser install', self.output.getvalue())

    def test_outdated_relay_requires_refresh(self):
        self.relay.write_text('old relay')
        self.assertFalse(self.run_status())

    def test_missing_extension_has_store_link_and_profile(self):
        self.extension.update(enabled=False, installed=False)
        self.assertFalse(self.run_status())
        self.assertIn('not found in Default', self.output.getvalue())
        self.assertIn('https://official.example/extension', self.output.getvalue())

    def test_disabled_extension_is_not_reinstalled(self):
        self.extension['enabled'] = False
        self.assertFalse(self.run_status())
        self.assertIn('Enable it at chrome://extensions', self.output.getvalue())


if __name__ == '__main__':
    unittest.main()
