"""Identity, required-file, architecture, and signature checks for macOS apps."""

import json
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from lcu.platforms import MAC_HELPER, MAC_REQUIRED_FILES, resolve_installed_mac_app


VERSION = '26.924.22138'
RUNTIME = '0.0.24/20260924074400-f52ea85e2a98'


class InstalledMacAppTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.app = Path(temporary.name) / 'ChatGPT.app'
        self.contents = self.app / 'Contents'
        self.resources = self.contents / 'Resources'
        self._plist(self.contents / 'Info.plist', 'com.openai.codex', VERSION)
        self._plist(self.contents / MAC_HELPER / 'Contents/Info.plist', 'com.openai.sky.CUAService')
        runtime = self.resources / 'cua_node/manifest.json'
        runtime.parent.mkdir(parents=True, exist_ok=True)
        runtime.write_text(json.dumps({'platform': 'darwin', 'arch': 'arm64',
                                       'runtime_archive_version': RUNTIME}))
        for relative in MAC_REQUIRED_FILES:
            path = self.contents / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(relative.encode())
            path.chmod(0o755)
        self.cli = self.resources / 'codex-cli/bin/codex'
        self.host = self.resources / 'codex-cli/bin/codex-code-mode-host'
        self.cli.parent.mkdir(parents=True, exist_ok=True)
        self.cli.write_bytes(b'original cli')
        self.host.write_bytes(b'original code-mode host')
        self.cli.chmod(0o755)
        self.host.chmod(0o755)

    @staticmethod
    def _plist(path, bundle_id, version=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        values = {'CFBundleIdentifier': bundle_id}
        if version:
            values['CFBundleShortVersionString'] = version
        with path.open('wb') as stream:
            plistlib.dump(values, stream)

    @staticmethod
    def _codesign(command, **_):
        if '--verify' in command:
            return subprocess.CompletedProcess(command, 0, '', '')
        bundle = Path(command[-1])
        identifier = 'com.openai.codex' if bundle.name == 'ChatGPT.app' else 'com.openai.sky.CUAService'
        return subprocess.CompletedProcess(command, 0, '',
                                           f'Identifier={identifier}\nTeamIdentifier=2DC432GLL2\n')

    def _resolve(self, **options):
        arguments = dict(arch='arm64')
        arguments.update(options)
        with patch('lcu.platforms.host_platform.system', return_value='Darwin'), \
             patch('lcu.platforms.subprocess.run', side_effect=self._codesign):
            return resolve_installed_mac_app(self.app, **arguments)

    def test_accepts_current_version_and_runtime_with_relocated_original_cli(self):
        result = self._resolve()
        self.assertEqual(result.app, self.app.resolve())
        self.assertEqual(result.resources, self.resources.resolve())
        self.assertEqual(result.runtime, (self.resources / 'cua_node').resolve())
        self.assertEqual((result.version, result.runtime_version, result.arch),
                         (VERSION, RUNTIME, 'arm64'))
        self.assertEqual((result.codex_cli, result.code_mode_host),
                         (self.cli.resolve(), self.host.resolve()))

    def test_accepts_compatible_update_without_old_version_runtime_or_hash_pins(self):
        self._plist(self.contents / 'Info.plist', 'com.openai.codex', '26.999.12345')
        manifest = self.resources / 'cua_node/manifest.json'
        manifest.write_text(json.dumps({'platform': 'darwin', 'arch': 'arm64',
                                        'runtime_archive_version': '0.0.99/new-runtime'}))
        self.cli.write_bytes(b'updated signed app CLI')
        result = self._resolve()
        self.assertEqual(result.version, '26.999.12345')
        self.assertEqual(result.runtime_version, '0.0.99/new-runtime')

    def test_accepts_legacy_complete_original_cli_layout(self):
        self.cli.unlink()
        self.host.unlink()
        self.cli = self.resources / 'codex'
        self.host = self.resources / 'codex-code-mode-host'
        self.cli.write_bytes(b'legacy cli')
        self.host.write_bytes(b'legacy code mode host')
        self.cli.chmod(0o755)
        self.host.chmod(0o755)
        result = self._resolve()
        self.assertEqual((result.codex_cli, result.code_mode_host),
                         (self.cli.resolve(), self.host.resolve()))

    def test_rejects_missing_required_file_and_partial_cli_layout(self):
        required = self.contents / MAC_REQUIRED_FILES[0]
        required.unlink()
        with self.assertRaisesRegex(ValueError, '(?i)required application file is missing'):
            self._resolve()
        required.write_bytes(MAC_REQUIRED_FILES[0].encode())
        required.chmod(0o755)
        self.cli.unlink()
        with self.assertRaisesRegex(ValueError, 'complete original Codex CLI layout'):
            self._resolve()

    def test_rejects_wrong_platform_identity_and_architecture(self):
        with patch('lcu.platforms.host_platform.system', return_value='Linux'):
            with self.assertRaisesRegex(ValueError, 'only be validated on macOS'):
                resolve_installed_mac_app(self.app, arch='arm64')
        with self.assertRaisesRegex(ValueError, 'Unsupported macOS architecture'):
            self._resolve(arch='x86')
        self._plist(self.contents / 'Info.plist', 'wrong.identifier', VERSION)
        with self.assertRaisesRegex(ValueError, 'Unexpected application bundle identifier'):
            self._resolve()

    def test_rejects_invalid_signer_or_signature(self):
        def invalid_signature(command, **kwargs):
            if '--verify' in command:
                return subprocess.CompletedProcess(command, 1, '', 'invalid')
            return self._codesign(command, **kwargs)

        with patch('lcu.platforms.host_platform.system', return_value='Darwin'), \
             patch('lcu.platforms.subprocess.run', side_effect=invalid_signature):
            with self.assertRaisesRegex(ValueError, 'signature verification failed'):
                resolve_installed_mac_app(self.app, arch='arm64')

        def wrong_team(command, **kwargs):
            result = self._codesign(command, **kwargs)
            return subprocess.CompletedProcess(command, result.returncode, result.stdout,
                                               result.stderr.replace('2DC432GLL2', 'another-team'))

        with patch('lcu.platforms.host_platform.system', return_value='Darwin'), \
             patch('lcu.platforms.subprocess.run', side_effect=wrong_team):
            with self.assertRaisesRegex(ValueError, 'signer does not match'):
                resolve_installed_mac_app(self.app, arch='arm64')


if __name__ == '__main__':
    unittest.main()
