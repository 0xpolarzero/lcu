"""Windows MSIX registration and sealed runtime selection (fixture only)."""

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from lcu.windows import (PACKAGE_NAME, PACKAGE_PUBLISHER, WINDOWS_REQUIRED_FILES,
                         _registered_package, application_inventory, inventory_sha256,
                         resolve_installed_windows_app, validate_windows_app_tree)


VERSION = '26.917.9434.0'
RUNTIME = '0.0.16/20260915001755-492f19756c31'


class InstalledWindowsPackageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.app = Path(temporary.name) / 'OpenAI.Codex_26.917.9434.0_x64'
        self.app.mkdir()
        self._write_identity(VERSION)
        for relative in WINDOWS_REQUIRED_FILES:
            file = self.app / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            data = relative.encode()
            if relative.endswith('cua_node/manifest.json'):
                data = json.dumps({'platform': 'windows', 'arch': 'x64',
                                   'runtime_archive_version': RUNTIME}).encode()
            file.write_bytes(data)
        self.package = {'Name': PACKAGE_NAME, 'Publisher': PACKAGE_PUBLISHER,
                        'Version': VERSION, 'Architecture': 'X64', 'SignatureKind': 'Store',
                        'InstallLocation': str(self.app)}

    def _write_identity(self, version):
        (self.app / 'AppxManifest.xml').write_text(
            f'<Package><Identity Name="{PACKAGE_NAME}" Publisher="{PACKAGE_PUBLISHER}" '
            f'Version="{version}" ProcessorArchitecture="x64"/></Package>')

    def _resolve(self, package=None):
        result = subprocess.CompletedProcess([], 0, json.dumps(package or self.package), '')
        with patch('lcu.windows.platform.system', return_value='Windows'), \
             patch('lcu.windows.platform.machine', return_value='AMD64'), \
             patch('lcu.windows.subprocess.run', return_value=result) as powershell:
            selected = resolve_installed_windows_app()
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
        self.assertEqual(selected.runtime_version, RUNTIME)
        self.assertEqual(selected.inventory_digest, inventory_sha256(selected.inventory))

    def test_validates_private_copy_without_querying_registration(self):
        private = self.app.parent / 'managed' / 'app'
        shutil.copytree(self.app, private)
        with patch('lcu.windows.platform.system', return_value='Windows'), \
             patch('lcu.windows.platform.machine', return_value='AMD64'), \
             patch('lcu.windows.subprocess.run') as powershell:
            selected = validate_windows_app_tree(private, expected_version=VERSION,
                expected_runtime=RUNTIME, expected_inventory=application_inventory(self.app))
        self.assertEqual(selected.app, private.resolve())
        powershell.assert_not_called()
        (private / WINDOWS_REQUIRED_FILES[2]).write_text('changed')
        with patch('lcu.windows.platform.system', return_value='Windows'), \
             patch('lcu.windows.platform.machine', return_value='AMD64'):
            with self.assertRaisesRegex(ValueError, 'differs from selected source inventory'):
                validate_windows_app_tree(private, expected_version=VERSION,
                    expected_runtime=RUNTIME, expected_inventory=application_inventory(self.app))

    def test_rejects_wrong_registration_before_using_package(self):
        with self.assertRaisesRegex(ValueError, 'official Windows x64 Store app'):
            self._resolve(package={**self.package, 'Publisher': 'CN=other'})
        with self.assertRaisesRegex(ValueError, 'version does not match its identity manifest'):
            self._resolve(package={**self.package, 'Version': '27.100.1.0'})
        with self.assertRaisesRegex(ValueError, 'official Windows x64 Store app'):
            self._resolve(package={**self.package, 'Architecture': 'ARM64'})
        with self.assertRaisesRegex(ValueError, 'official Windows x64 Store app'):
            self._resolve(package={**self.package, 'SignatureKind': 'Developer'})

    def test_accepts_new_official_version_and_records_source_inventory(self):
        version = '27.100.1.0'
        self._write_identity(version)
        selected = self._resolve(package={**self.package, 'Version': version})
        self.assertEqual(selected.version, version)

    def test_query_projects_typed_powershell_properties_to_strings(self):
        result = subprocess.CompletedProcess([], 0, json.dumps(self.package), '')
        with patch('lcu.windows.subprocess.run', return_value=result) as powershell:
            self.assertEqual(_registered_package(), self.package)
        command = powershell.call_args.args[0][-1]
        self.assertIn("$_.Version.ToString()", command)
        self.assertIn("$_.Architecture.ToString()", command)
        self.assertIn("$_.SignatureKind.ToString()", command)
        for unprojected in ({**self.package, 'Version': {'Major': 26, 'Minor': 917}},
                            {**self.package, 'Architecture': 9},
                            {**self.package, 'SignatureKind': 0}):
            raw = subprocess.CompletedProcess([], 0, json.dumps(unprojected), '')
            with patch('lcu.windows.subprocess.run', return_value=raw):
                with self.assertRaisesRegex(ValueError, 'string version, architecture and signature kind'):
                    _registered_package()

    def test_selected_tree_inventory_rejects_modified_file(self):
        inventory = application_inventory(self.app)
        (self.app / WINDOWS_REQUIRED_FILES[2]).write_text('modified')
        with patch('lcu.windows.platform.system', return_value='Windows'), \
             patch('lcu.windows.platform.machine', return_value='AMD64'):
            with self.assertRaisesRegex(ValueError, 'differs from selected source inventory'):
                validate_windows_app_tree(self.app, expected_version=VERSION,
                    expected_runtime=RUNTIME, expected_inventory=inventory)

    def test_accepts_msix_encoded_scoped_module_segment(self):
        original = self.app / WINDOWS_REQUIRED_FILES[5]
        encoded = self.app / WINDOWS_REQUIRED_FILES[5].replace('@oai/', '%40oai/')
        encoded.parent.mkdir(parents=True, exist_ok=True)
        original.rename(encoded)
        self.assertEqual(self._resolve().launcher, encoded.resolve())

    def test_rejects_redirected_required_file(self):
        target = self.app.parent / 'external-cua-node'
        original = self.app / 'app/resources/cua_node'
        original.rename(target)
        original.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'redirected path'):
            self._resolve()

    def test_rejects_required_file_through_junction(self):
        junction = (self.app / 'app/resources/cua_node').resolve()
        with patch.object(Path, 'is_junction', autospec=True,
                          side_effect=lambda path: path == junction):
            with self.assertRaisesRegex(ValueError, 'missing or outside the app'):
                self._resolve()

    def test_rejects_wrong_runtime_and_host_platform(self):
        with patch('lcu.windows.platform.system', return_value='Darwin'):
            with self.assertRaisesRegex(ValueError, 'only be validated on Windows x64'):
                resolve_installed_windows_app()
        with patch('lcu.windows.platform.system', return_value='Windows'), \
             patch('lcu.windows.platform.machine', return_value='AMD64'):
            with self.assertRaisesRegex(ValueError, 'runtime changed after selection'):
                validate_windows_app_tree(self.app, expected_version=VERSION,
                    expected_runtime='wrong', expected_inventory=application_inventory(self.app))


if __name__ == '__main__':
    unittest.main()
