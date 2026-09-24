"""Pin and signature checks for an installed macOS CUA runtime."""

import hashlib
import json
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from lcu.platforms import MAC_HELPER, MAC_REQUIRED_FILES, resolve_installed_mac_app


VERSION = '26.917.62051'
RUNTIME = '0.0.16/20260915001755-492f19756c31'


class InstalledMacAppTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.app = Path(self.temporary.name) / 'ChatGPT.app'
        self.contents = self.app / 'Contents'
        self._plist(self.contents / 'Info.plist', 'com.openai.codex', VERSION)
        self._plist(self.contents / MAC_HELPER / 'Contents/Info.plist', 'com.openai.sky.CUAService')
        runtime = self.contents / 'Resources/cua_node/manifest.json'
        runtime.parent.mkdir(parents=True, exist_ok=True)
        runtime.write_text(json.dumps({'platform': 'darwin', 'arch': 'arm64',
                                       'runtime_archive_version': RUNTIME}))
        self.hashes = {}
        for relative in MAC_REQUIRED_FILES:
            path = self.contents / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            data = relative.encode()
            path.write_bytes(data)
            path.chmod(0o755)
            self.hashes[relative] = hashlib.sha256(data).hexdigest()

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
        arguments = dict(expected_version=VERSION, expected_runtime=RUNTIME,
                         expected_hashes=self.hashes, arch='arm64')
        arguments.update(options)
        with patch('lcu.platforms.host_platform.system', return_value='Darwin'), \
             patch('lcu.platforms.subprocess.run', side_effect=self._codesign):
            return resolve_installed_mac_app(self.app, **arguments)

    def test_resolves_complete_pinned_app_without_copying_it(self):
        self.assertEqual(MAC_HELPER.parts[0], 'Resources')
        self.assertTrue(all(Path(relative).parts[0] == 'Resources'
                            for relative in MAC_REQUIRED_FILES))
        result = self._resolve()
        self.assertEqual(result.app, self.app.resolve())
        self.assertEqual(result.resources, (self.contents / 'Resources').resolve())
        self.assertEqual(result.runtime, (self.contents / 'Resources/cua_node').resolve())
        self.assertEqual((result.backend, result.version, result.arch), ('mac', VERSION, 'arm64'))

    def test_rejects_unpinned_or_modified_runtime_file(self):
        with self.assertRaisesRegex(ValueError, 'pins must cover'):
            self._resolve(expected_hashes={})
        (self.contents / MAC_REQUIRED_FILES[0]).write_text('modified')
        with self.assertRaisesRegex(ValueError, 'does not match pin'):
            self._resolve()

    def test_rejects_wrong_platform_runtime_and_version(self):
        with self.assertRaisesRegex(ValueError, 'version does not match pin'):
            self._resolve(expected_version='wrong')
        with self.assertRaisesRegex(ValueError, 'runtime does not match pin'):
            self._resolve(expected_runtime='wrong')
        with patch('lcu.platforms.host_platform.system', return_value='Linux'):
            with self.assertRaisesRegex(ValueError, 'only be validated on macOS'):
                resolve_installed_mac_app(self.app, expected_version=VERSION,
                                          expected_runtime=RUNTIME, expected_hashes=self.hashes)

    def test_rejects_invalid_signer_or_signature(self):
        def invalid_signature(command, **kwargs):
            if '--verify' in command:
                return subprocess.CompletedProcess(command, 1, '', 'invalid')
            return self._codesign(command, **kwargs)

        with patch('lcu.platforms.host_platform.system', return_value='Darwin'), \
             patch('lcu.platforms.subprocess.run', side_effect=invalid_signature):
            with self.assertRaisesRegex(ValueError, 'signature verification failed'):
                resolve_installed_mac_app(self.app, expected_version=VERSION,
                                          expected_runtime=RUNTIME, expected_hashes=self.hashes,
                                          arch='arm64')

        def wrong_team(command, **kwargs):
            result = self._codesign(command, **kwargs)
            return subprocess.CompletedProcess(command, result.returncode, result.stdout,
                                               result.stderr.replace('2DC432GLL2', 'another-team'))

        with patch('lcu.platforms.host_platform.system', return_value='Darwin'), \
             patch('lcu.platforms.subprocess.run', side_effect=wrong_team):
            with self.assertRaisesRegex(ValueError, 'signer does not match'):
                resolve_installed_mac_app(self.app, expected_version=VERSION,
                                          expected_runtime=RUNTIME, expected_hashes=self.hashes,
                                          arch='arm64')


if __name__ == '__main__':
    unittest.main()
