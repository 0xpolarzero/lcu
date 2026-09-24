"""Native-host setup tests use only disposable homes and a fake upstream installer."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lcu.browser import _manifest_paths, install


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


if __name__ == '__main__':
    unittest.main()
