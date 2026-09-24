"""Windows archive and stable-release selection are thin and platform specific."""

import json
import hashlib
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
from bundle import architecture
from lcu.windows import WINDOWS_REQUIRED_FILES


class WindowsBuildTests(unittest.TestCase):
    def test_native_windows_amd64_name_selects_x64_archive(self):
        with mock.patch('bundle.platform.system', return_value='Windows'), \
             mock.patch('bundle.platform.machine', return_value='AMD64'):
            self.assertEqual(architecture('windows'), 'x64')

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
                             'scripts/windows_launcher.py', 'bundle.json',
                             'docs/verification/codex-interactive-2026-09-24.md'):
                    self.assertIn(prefix + name, names)
                bundled_records = {name.removeprefix(prefix + 'docs/verification/') for name in names
                                   if name.startswith(prefix + 'docs/verification/')}
                source_records = {path.name for path in (ROOT / 'docs/verification').glob('*.md')}
                self.assertEqual(bundled_records, source_records)
                self.assertFalse(any(name.startswith(prefix + 'docs/verification/')
                                     and not name.endswith('.md') for name in names))
                manifest = json.loads(bundle.read(prefix + 'bundle.json'))
                self.assertEqual((manifest['platform'], manifest['architecture']), ('windows', 'x64'))
                self.assertFalse(any(name.startswith(prefix + 'app/') for name in names))
                self.assertFalse(any(name.endswith(('.exe', '.msix', '.node')) for name in names))
                for path in ('bin/lcu-session', 'lcu/session.py', 'scripts/install.sh', 'scripts/install.py',
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
                'architectures': {'x64': {'sha256': 'fixture',
                    'components': {'app/resources/app.asar': 'fixture'}}}}}}))
            prefix = base / 'installed'
            official = base / 'official-app'
            official.mkdir()
            (official / 'notice.txt').write_text('original notice')
            with mock.patch.object(install_windows, 'SOURCE', source), \
                 mock.patch.object(install_windows.platform, 'system', return_value='Windows'), \
                 mock.patch.object(install_windows.sys, 'version_info', (3, 13)), \
                 mock.patch.object(install_windows.sys, 'executable', 'C:\\Python313\\python.exe'), \
                 mock.patch.object(install_windows, 'architecture', return_value='x64'), \
                 mock.patch.object(install_windows, 'verify'), \
                 mock.patch.object(install_windows, 'checked_prefix', return_value=prefix), \
                 mock.patch.object(install_windows, 'resolve_installed_windows_app',
                                   return_value=SimpleNamespace(app=official)), \
                 mock.patch.object(install_windows, '_validated_copy'), \
                 mock.patch.object(install_windows, 'materialize_original_host'), \
                 mock.patch('lcu.runtime.paths', return_value=(base / 'official-app', None, None, {})):
                install_windows.install(prefix)
            wrapper = (prefix / 'lcu.cmd').read_text()
            self.assertIn('"C:\\Python313\\python.exe" -B', wrapper)
            self.assertNotIn('py -3.12', wrapper)

    def test_installer_stages_full_package_and_keeps_current_on_invalid_generation(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / 'archive'
            (source / 'scripts').mkdir(parents=True)
            (source / 'scripts/windows_launcher.py').write_text('fixture')
            official = base / 'official-app'
            hashes = {}
            for relative in WINDOWS_REQUIRED_FILES:
                file = official / relative
                file.parent.mkdir(parents=True, exist_ok=True)
                data = relative.encode()
                if relative.endswith('cua_node/manifest.json'):
                    data = json.dumps({'platform': 'windows', 'arch': 'x64',
                        'runtime_archive_version': 'runtime-fixture'}).encode()
                file.write_bytes(data)
                hashes[relative] = hashlib.sha256(data).hexdigest()
            (official / 'app/resources/NOTICE.txt').write_text('original notice')
            (source / 'runtime.lock.json').write_text(json.dumps({'platforms': {'windows': {
                'version': '26.917.9434.0', 'runtime': 'runtime-fixture',
                'architectures': {'x64': {'sha256': 'a' * 64, 'components': hashes}}}}}))
            prefix = base / 'installed'
            with mock.patch.object(install_windows, 'SOURCE', source), \
                 mock.patch.object(install_windows.platform, 'system', return_value='Windows'), \
                 mock.patch.object(install_windows.sys, 'version_info', (3, 13)), \
                 mock.patch.object(install_windows, 'architecture', return_value='x64'), \
                 mock.patch.object(install_windows, 'verify'), \
                 mock.patch.object(install_windows, 'checked_prefix', return_value=prefix), \
                 mock.patch.object(install_windows, 'resolve_installed_windows_app',
                                   return_value=SimpleNamespace(app=official)), \
                 mock.patch('lcu.windows.platform.system', return_value='Windows'), \
                 mock.patch('lcu.windows.platform.machine', return_value='AMD64'), \
                 mock.patch.object(install_windows, 'materialize_original_host'), \
                 mock.patch('lcu.runtime.paths'):
                install_windows.install(prefix)
                descriptor = json.loads((prefix / 'current.json').read_text())
                release = prefix / 'releases' / descriptor['release']
                app = Path(json.loads((release / 'installation.json').read_text())['app'])
                self.assertEqual(app.parent, prefix / 'apps' / ('26.917.9434.0-x64-' + 'a' * 16))
                self.assertEqual((app / 'app/resources/NOTICE.txt').read_text(), 'original notice')
                self.assertEqual((official / 'app/resources/NOTICE.txt').read_text(), 'original notice')
                install_windows.install(prefix)
                descriptor = json.loads((prefix / 'current.json').read_text())
                self.assertEqual(Path(json.loads((prefix / 'releases' /
                    descriptor['release'] /
                    'installation.json').read_text())['app']), app)
                original_lock = (source / 'runtime.lock.json').read_text()
                changed_lock = json.loads(original_lock)
                changed_lock['platforms']['windows']['architectures']['x64']['sha256'] = 'b' * 64
                (source / 'runtime.lock.json').write_text(json.dumps(changed_lock))
                with mock.patch.object(install_windows, '_validated_copy',
                                       side_effect=ValueError('copied bytes changed')):
                    with self.assertRaisesRegex(ValueError, 'copied bytes changed'):
                        install_windows.install(prefix)
                self.assertFalse(list((prefix / 'apps').glob('*.stage')))
                self.assertEqual(json.loads((prefix / 'current.json').read_text()), descriptor)
                self.assertEqual((app / 'app/resources/NOTICE.txt').read_text(), 'original notice')
                (source / 'runtime.lock.json').write_text(original_lock)
                (app / WINDOWS_REQUIRED_FILES[2]).write_text('tampered')
                with self.assertRaisesRegex(ValueError, 'does not match pin'):
                    install_windows.install(prefix)
                self.assertEqual(json.loads((prefix / 'current.json').read_text()), descriptor)

    def test_rejects_redirected_prefix_ancestor(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            link = base / 'junction'
            target = base / 'other'
            target.mkdir()
            link.symlink_to(target, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'linked Windows installation path'):
                install_windows.checked_prefix(link / 'lcu')

    def test_rejects_windows_junction_prefix_ancestor(self):
        with tempfile.TemporaryDirectory() as temporary:
            prefix = Path(temporary) / 'junction' / 'lcu'
            junction = prefix.parent
            with mock.patch.object(Path, 'is_junction', autospec=True,
                                   side_effect=lambda path: path == junction):
                with self.assertRaisesRegex(ValueError, 'linked Windows installation path'):
                    install_windows.checked_prefix(prefix)


if __name__ == '__main__':
    unittest.main()
