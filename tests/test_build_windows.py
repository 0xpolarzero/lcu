"""Windows archive and stable-release selection are thin and platform specific."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from zipfile import ZipFile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_bundle
import install_windows
import windows_launcher


class WindowsBuildTests(unittest.TestCase):
    def test_cross_built_windows_archive_omits_upstream_payload_and_node(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'dist'
            def fake_provision(release, _source, **options):
                self.assertEqual(options['target'], 'windows')
                (release / 'agent-tools/node_modules/skills').mkdir(parents=True)
                (release / 'agent-tools/node_modules/skills/package.json').write_text('{}')
            with mock.patch.object(build_bundle, 'provision_agents', side_effect=fake_provision):
                archive = build_bundle.build(output, target='windows')
            self.assertEqual(archive.name, 'lcu-0.3.0-windows-x64.zip')
            with ZipFile(archive) as bundle:
                names = set(bundle.namelist())
                prefix = 'lcu-0.3.0-windows-x64/'
                for name in ('bin/lcu.cmd', 'lcu/windows.py', 'scripts/install_windows.py',
                             'scripts/windows_launcher.py', 'bundle.json'):
                    self.assertIn(prefix + name, names)
                manifest = json.loads(bundle.read(prefix + 'bundle.json'))
                self.assertEqual((manifest['platform'], manifest['architecture']), ('windows', 'x64'))
                self.assertFalse(any(name.startswith(prefix + 'app/') for name in names))
                self.assertFalse(any(name.endswith(('.exe', '.msix', '.node')) for name in names))
                for path in ('bin/lcu-session', 'scripts/install.sh', 'scripts/install.py',
                             'scripts/installed_app.py'):
                    self.assertNotIn(prefix + path, names)

    def test_windows_launcher_rejects_pointer_escape_and_selects_versioned_release(self):
        with tempfile.TemporaryDirectory() as temporary:
            prefix = Path(temporary).resolve()
            release = prefix / 'releases' / '0.3.0-123abc'
            (release / 'bin').mkdir(parents=True)
            (release / 'bin/lcu').write_text('fixture')
            (prefix / 'current.json').write_text(json.dumps({'release': release.name}))
            self.assertEqual(windows_launcher.selected_release(prefix), release)
            (prefix / 'current.json').write_text(json.dumps({'release': '../elsewhere'}))
            with self.assertRaisesRegex(ValueError, 'Invalid selected'):
                windows_launcher.selected_release(prefix)

    def test_installer_selects_registered_msix_before_mutating_prefix(self):
        with tempfile.TemporaryDirectory() as temporary:
            prefix = Path(temporary).resolve() / 'install'
            with mock.patch.object(install_windows.platform, 'system', return_value='Windows'), \
                 mock.patch.object(install_windows, 'architecture', return_value='x64'), \
                 mock.patch.object(install_windows, 'verify'), \
                 mock.patch.object(install_windows, 'resolve_installed_windows_app',
                                   side_effect=ValueError('MSIX is not registered')):
                with self.assertRaisesRegex(ValueError, 'MSIX is not registered'):
                    install_windows.install(prefix)
            self.assertFalse(prefix.exists())

    def test_installed_launcher_reuses_validated_python_313(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / 'archive'
            (source / 'scripts').mkdir(parents=True)
            (source / 'scripts/windows_launcher.py').write_text('fixture')
            (source / 'runtime.lock.json').write_text(json.dumps({'platforms': {'windows': {
                'version': '26.917.9434.0', 'runtime': '24.21.0',
                'architectures': {'x64': {'sha256': 'fixture', 'components': {}}}}}}))
            prefix = base / 'installed'
            with mock.patch.object(install_windows, 'SOURCE', source), \
                 mock.patch.object(install_windows.platform, 'system', return_value='Windows'), \
                 mock.patch.object(install_windows.sys, 'version_info', (3, 13)), \
                 mock.patch.object(install_windows.sys, 'executable', 'C:\\Python313\\python.exe'), \
                 mock.patch.object(install_windows, 'architecture', return_value='x64'), \
                 mock.patch.object(install_windows, 'verify'), \
                 mock.patch.object(install_windows, 'checked_prefix', return_value=prefix), \
                 mock.patch.object(install_windows, 'resolve_installed_windows_app',
                                   return_value=SimpleNamespace(app=base / 'official-app')), \
                 mock.patch('lcu.runtime.paths', return_value=(base / 'official-app', None, None, {})):
                install_windows.install(prefix)
            wrapper = (prefix / 'lcu.cmd').read_text()
            self.assertIn('"C:\\Python313\\python.exe" -B', wrapper)
            self.assertNotIn('py -3.12', wrapper)


if __name__ == '__main__':
    unittest.main()
