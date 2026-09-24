"""Windows MSIX registration and sealed runtime selection (fixture only)."""

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from lcu.windows import (PACKAGE_NAME, PACKAGE_PUBLISHER, WINDOWS_REQUIRED_FILES,
                         _registered_package,
                         resolve_installed_windows_app)


VERSION = '26.917.9434.0'
RUNTIME = '0.0.16/20260915001755-492f19756c31'


class InstalledWindowsPackageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.app = Path(temporary.name) / 'OpenAI.Codex_26.917.9434.0_x64'
        self.hashes = {}
        for relative in WINDOWS_REQUIRED_FILES:
            file = self.app / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            data = relative.encode()
            if relative.endswith('cua_node/manifest.json'):
                data = json.dumps({'platform': 'windows', 'arch': 'x64',
                                   'runtime_archive_version': RUNTIME}).encode()
            file.write_bytes(data)
            self.hashes[relative] = hashlib.sha256(data).hexdigest()
        self.package = {'Name': PACKAGE_NAME, 'Publisher': PACKAGE_PUBLISHER,
                        'Version': VERSION, 'Architecture': 'X64',
                        'InstallLocation': str(self.app)}

    def _resolve(self, package=None, **options):
        kwargs = {'expected_version': VERSION, 'expected_runtime': RUNTIME,
                  'expected_hashes': self.hashes}
        kwargs.update(options)
        result = subprocess.CompletedProcess([], 0, json.dumps(package or self.package), '')
        with patch('lcu.windows.platform.system', return_value='Windows'), \
             patch('lcu.windows.platform.machine', return_value='AMD64'), \
             patch('lcu.windows.subprocess.run', return_value=result) as powershell:
            selected = resolve_installed_windows_app(**kwargs)
        powershell.assert_called_once()
        self.assertIn('Get-AppxPackage', powershell.call_args.args[0][-1])
        return selected

    def test_selects_original_registered_package_without_copying(self):
        selected = self._resolve()
        self.assertEqual(selected.app, self.app.resolve())
        self.assertEqual(selected.resources, self.app.resolve() / 'app/resources')
        self.assertEqual(selected.runtime, self.app.resolve() / 'app/resources/cua_node')
        self.assertEqual(selected.launcher, self.app.resolve() / WINDOWS_REQUIRED_FILES[5])
        self.assertEqual((selected.backend, selected.version, selected.arch),
                         ('windows', VERSION, 'x64'))

    def test_rejects_wrong_registration_before_using_package(self):
        with self.assertRaisesRegex(ValueError, 'does not match'):
            self._resolve(package={**self.package, 'Publisher': 'CN=other'})
        with self.assertRaisesRegex(ValueError, 'does not match'):
            self._resolve(package={**self.package, 'Version': 'newer'})
        with self.assertRaisesRegex(ValueError, 'does not match'):
            self._resolve(package={**self.package, 'Architecture': 'ARM64'})

    def test_query_projects_typed_powershell_properties_to_strings(self):
        result = subprocess.CompletedProcess([], 0, json.dumps(self.package), '')
        with patch('lcu.windows.subprocess.run', return_value=result) as powershell:
            self.assertEqual(_registered_package(), self.package)
        command = powershell.call_args.args[0][-1]
        self.assertIn("$_.Version.ToString()", command)
        self.assertIn("$_.Architecture.ToString()", command)
        for unprojected in ({**self.package, 'Version': {'Major': 26, 'Minor': 917}},
                            {**self.package, 'Architecture': 9}):
            raw = subprocess.CompletedProcess([], 0, json.dumps(unprojected), '')
            with patch('lcu.windows.subprocess.run', return_value=raw):
                with self.assertRaisesRegex(ValueError, 'string version and architecture'):
                    _registered_package()

    def test_rejects_incomplete_pins_and_modified_file(self):
        with self.assertRaisesRegex(ValueError, 'pins must cover'):
            self._resolve(expected_hashes={})
        (self.app / WINDOWS_REQUIRED_FILES[2]).write_text('modified')
        with self.assertRaisesRegex(ValueError, 'does not match pin'):
            self._resolve()

    def test_accepts_msix_encoded_scoped_module_segment(self):
        original = self.app / WINDOWS_REQUIRED_FILES[5]
        encoded = self.app / WINDOWS_REQUIRED_FILES[5].replace('@oai/', '%40oai/')
        encoded.parent.mkdir(parents=True, exist_ok=True)
        original.rename(encoded)
        self.assertEqual(self._resolve().launcher, encoded.resolve())

    def test_rejects_wrong_runtime_and_host_platform(self):
        with self.assertRaisesRegex(ValueError, 'runtime does not match pin'):
            self._resolve(expected_runtime='wrong')
        with patch('lcu.windows.platform.system', return_value='Darwin'):
            with self.assertRaisesRegex(ValueError, 'only be validated on Windows x64'):
                resolve_installed_windows_app(expected_version=VERSION,
                    expected_runtime=RUNTIME, expected_hashes=self.hashes)


if __name__ == '__main__':
    unittest.main()
