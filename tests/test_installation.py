import os
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
from lcu.runtime import environment
from lcu.session import discover
from lcu.setup import Change, apply_changes, regular_path
from install import checked_prefix, install, main as install_main
from installed_app import (_cached_package, _check_package_identity, _validate_app,
                           _download, preflight as preflight_app, provision as provision_app,
                           _validate_managed)
from bundle import seal


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def test_foreign_prefix_is_untouched(self):
        (self.root / 'keep').write_text('valuable')
        with self.assertRaises(ValueError):
            checked_prefix(self.root)
        self.assertEqual((self.root / 'keep').read_text(), 'valuable')

    def test_symlink_destination_is_rejected(self):
        (self.root / 'link').symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            checked_prefix(self.root / 'link/lcu')

    def test_relative_prefix_is_rejected(self):
        with self.assertRaises(ValueError):
            checked_prefix(Path('relative/lcu'))

    def test_offline_requires_skip_system_before_installation_writes(self):
        with patch('install.setup.validate', side_effect=AssertionError('setup reached')), \
             patch('install.subprocess.run', side_effect=AssertionError('network reached')):
            with self.assertRaisesRegex(ValueError, '--offline requires --skip-system'):
                install_main(['--offline', '--runtime-only'])

    def test_installation_inside_its_source_bundle_is_rejected(self):
        with patch('install.SOURCE', self.root):
            with self.assertRaisesRegex(ValueError, 'outside'):
                checked_prefix(self.root / 'nested-prefix')

    def test_corrupt_download_never_executes(self):
        source = self.root / 'source'
        source.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            _download({'source': source.as_uri()}, {'deb_arch': 'arm64', 'sha256': '0' * 64},
                      self.root / 'download')

    def test_offline_app_install_requires_a_verified_local_source(self):
        prefix = self.root / 'lcu'
        prefix.mkdir()
        lock = {'version': '26.915.31945', 'runtime': 'runtime-pin',
                'source': 'https://invalid/{deb_arch}.deb',
                'architectures': {'arm64': {'deb_arch': 'arm64', 'sha256': 'a' * 64}}}
        (self.root / 'runtime.lock.json').write_text(json.dumps(lock))
        with self.assertRaisesRegex(ValueError, '--offline requires'):
            provision_app(prefix, 'arm64', offline=True, root=self.root)
        self.assertEqual(list((prefix / 'apps').iterdir()), [])

    def test_validated_package_cache_is_reused_offline_and_corruption_fails_closed(self):
        prefix = self.root / 'lcu'
        prefix.mkdir()
        source = self.root / 'official.deb'
        source.write_bytes(b'pinned package bytes')
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        lock = {'version': '26.915.31945'}
        entry = {'sha256': digest}
        cached = _cached_package(prefix, 'arm64', lock, entry, package=source)
        self.assertEqual(cached.read_bytes(), source.read_bytes())
        self.assertEqual(_cached_package(prefix, 'arm64', lock, entry, offline=True), cached)
        cached.write_bytes(b'corrupt cache')
        with self.assertRaisesRegex(ValueError, 'Cached application package is corrupt'):
            _cached_package(prefix, 'arm64', lock, entry, offline=True)

    def test_interrupted_package_staging_recovers_without_network(self):
        prefix = self.root / 'lcu'
        prefix.mkdir()
        source = self.root / 'official.deb'
        source.write_bytes(b'pinned package bytes')
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        lock = {'version': '26.915.31945', 'source': 'https://invalid/{deb_arch}.deb'}
        entry = {'sha256': digest, 'deb_arch': 'arm64'}
        name = f"chatgpt_{lock['version']}_arm64_{digest[:16]}.deb"
        cache = prefix / 'cache'
        cache.mkdir()
        stage = cache / ('.' + name + '.stage')
        stage.write_bytes(b'interrupted copy')
        cached = _cached_package(prefix, 'arm64', lock, entry, package=source)
        self.assertEqual(cached.read_bytes(), source.read_bytes())
        self.assertFalse(stage.exists())
        cached.unlink()
        download = cache / ('.' + name + '.download')
        download.write_bytes(source.read_bytes())
        with patch('installed_app._download', side_effect=AssertionError('network used')):
            self.assertEqual(_cached_package(prefix, 'arm64', lock, entry, offline=True), cached)
        self.assertEqual(cached.read_bytes(), source.read_bytes())
        self.assertFalse(download.exists())

    def test_wrong_local_package_is_rejected_before_deb_extraction(self):
        prefix = self.root / 'lcu'
        package = self.root / 'wrong.deb'
        prefix.mkdir()
        package.write_bytes(b'not the pinned package')
        lock = {'version': '26.915.31945', 'runtime': 'runtime-pin',
                'source': 'https://invalid/{deb_arch}.deb',
                'architectures': {'arm64': {'deb_arch': 'arm64', 'sha256': 'a' * 64}}}
        (self.root / 'runtime.lock.json').write_text(json.dumps(lock))
        with patch('installed_app.subprocess.run') as run:
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                provision_app(prefix, 'arm64', package=package, root=self.root)
        run.assert_not_called()
        self.assertEqual(list((prefix / 'apps').iterdir()), [])

    def test_existing_app_with_wrong_component_bytes_is_rejected(self):
        app = self.root / 'chatgpt'
        runtime = app / 'resources/cua_node'
        for relative in (
            'ChatGPT', 'resources/app.asar', 'resources/codex', 'resources/codex-code-mode-host',
            'resources/cua_node/bin/node', 'resources/cua_node/bin/node_repl',
            'resources/plugins/openai-bundled/plugins/browser/placeholder',
            'resources/plugins/openai-bundled/plugins/chrome/.codex-plugin/plugin.json',
            'resources/plugins/openai-bundled/plugins/chrome/extension-host/linux/arm64/extension-host',
            'resources/plugins/openai-bundled/plugins/unified-computer-use/.mcp.json',
        ):
            path = app / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'wrong bytes')
            path.chmod(0o755)
        (runtime / 'manifest.json').write_text(
            '{"platform":"linux","arch":"arm64","runtime_archive_version":"runtime-pin"}')
        lock = {'version': '26.915.31945', 'runtime': 'runtime-pin',
                'architectures': {'arm64': {'components': {'resources/app.asar': '0' * 64}}}}
        with self.assertRaisesRegex(ValueError, 'does not match runtime.lock.json'):
            _validate_app(app, 'arm64', lock, lock['version'])

    def test_existing_app_modified_browser_installer_is_rejected_by_package_baseline(self):
        app = self.root / 'chatgpt'
        browser = app / 'resources/plugins/openai-bundled/plugins/browser/install.js'
        browser.parent.mkdir(parents=True)
        browser.write_text('modified installer')
        lock = {'version': '26.915.31945', 'runtime': 'runtime-pin', 'source': 'unused',
                'architectures': {'arm64': {'deb_arch': 'arm64', 'sha256': 'a' * 64}}}
        (self.root / 'runtime.lock.json').write_text(json.dumps(lock))
        expected = {'.': {'type': 'directory', 'mode': 0o755},
                    'resources': {'type': 'directory', 'mode': 0o755},
                    'resources/plugins': {'type': 'directory', 'mode': 0o755},
                    'resources/plugins/openai-bundled': {'type': 'directory', 'mode': 0o755},
                    'resources/plugins/openai-bundled/plugins': {'type': 'directory', 'mode': 0o755},
                    'resources/plugins/openai-bundled/plugins/browser': {'type': 'directory', 'mode': 0o755},
                    'resources/plugins/openai-bundled/plugins/browser/install.js':
                        {'type': 'file', 'mode': 0o644, 'sha256': hashlib.sha256(b'official').hexdigest()}}
        with patch('installed_app._cached_package', return_value=self.root / 'official.deb'), \
             patch('installed_app._package_inventory', return_value=expected), \
             patch('installed_app._validate_app', return_value={}):
            with self.assertRaisesRegex(ValueError, 'does not match the verified official package'):
                preflight_app(self.root / 'lcu', 'arm64', existing_app=app, root=self.root)

    def test_managed_generation_inventory_drift_is_rejected(self):
        generation = self.root / 'generation'
        app = generation / 'payload/usr/lib/chatgpt'
        browser = app / 'resources/plugins/openai-bundled/plugins/browser/install.js'
        browser.parent.mkdir(parents=True)
        browser.write_text('changed')
        lock = {'version': '26.915.31945', 'runtime': 'runtime-pin'}
        entry = {'sha256': 'a' * 64}
        (generation / 'installed.json').write_text(json.dumps({
            'package_version': lock['version'], 'architecture': 'arm64',
            'sha256': entry['sha256'], 'application': 'payload/usr/lib/chatgpt',
            'inventory': {'.': {'type': 'directory', 'mode': 0o755}}}))
        with patch('installed_app._validate_app', return_value={}):
            self.assertFalse(_validate_managed(generation, 'arm64', lock, entry, execute=False))

    def test_offline_existing_app_requires_valid_official_package_baseline(self):
        app = self.root / 'chatgpt'
        app.mkdir()
        lock = {'version': '26.915.31945', 'runtime': 'runtime-pin', 'source': 'unused',
                'architectures': {'arm64': {'deb_arch': 'arm64', 'sha256': 'a' * 64}}}
        (self.root / 'runtime.lock.json').write_text(json.dumps(lock))
        with patch('installed_app._cached_package', side_effect=ValueError('--offline requires a valid cached application package')):
            with self.assertRaisesRegex(ValueError, '--offline requires'):
                preflight_app(self.root / 'lcu', 'arm64', existing_app=app, offline=True, root=self.root)

    def test_dpkg_deb_labeled_identity_output_is_parsed_exactly(self):
        lock = {'version': '26.915.31945'}
        _check_package_identity(
            'Package: chatgpt\nVersion: 26.915.31945\nArchitecture: arm64\n', 'arm64', lock)
        with self.assertRaisesRegex(ValueError, 'Unexpected official package identity'):
            _check_package_identity(
                'Package: unrelated\nVersion: 26.915.31945\nArchitecture: arm64\n', 'arm64', lock)

    def test_failed_upgrade_preserves_active_release(self):
        prefix = self.root / 'lcu'
        old = prefix / 'releases/old'
        old.mkdir(parents=True)
        (old / 'data').write_text('previous version')
        (prefix / '.lcu-install').touch()
        (prefix / 'current').symlink_to('releases/old')
        source = self.root / 'bundle'
        source.mkdir()
        (source / 'payload').write_text('new version')
        (source / 'runtime.lock.json').write_text(json.dumps({
            'version': '26.915.31945', 'architectures': {'arm64': {'sha256': '0' * 64}}}))
        seal(source, 'arm64')
        application = self.root / 'chatgpt'
        application.mkdir()
        with patch('install.SOURCE', source), patch('install.architecture', return_value='arm64'), \
             patch('install.provision_app', return_value=(application, None)), \
             patch('install.validate_release', side_effect=ValueError('runtime validation failed')):
            with self.assertRaisesRegex(ValueError, 'runtime validation failed'):
                install(prefix)
        self.assertEqual((prefix / 'current/data').read_text(), 'previous version')
        self.assertEqual(list((prefix / 'releases').iterdir()), [old])
        self.assertFalse(list(prefix.glob('.build-*')))

    def test_simultaneous_installs_to_same_prefix_serialize_release_switches(self):
        prefix = self.root / 'lcu'
        old = prefix / 'releases/old'
        old.mkdir(parents=True)
        (old / 'data').write_text('previous version')
        (prefix / '.lcu-install').touch()
        (prefix / 'current').symlink_to('releases/old')
        source = self.root / 'bundle'
        source.mkdir()
        (source / 'payload').write_text('new version')
        (source / 'runtime.lock.json').write_text(json.dumps({
            'version': '26.915.31945', 'architectures': {'arm64': {'sha256': '0' * 64}}}))
        seal(source, 'arm64')
        application = self.root / 'chatgpt'
        application.mkdir()

        start = threading.Barrier(2)
        state_lock = threading.Lock()
        active_validations = 0
        max_active_validations = 0
        errors = []

        def validate(_release, _account=None):
            nonlocal active_validations, max_active_validations
            with state_lock:
                active_validations += 1
                max_active_validations = max(max_active_validations, active_validations)
            time.sleep(0.05)
            with state_lock:
                active_validations -= 1

        def run_install():
            try:
                start.wait(timeout=5)
                install(prefix)
            except BaseException as exc:
                errors.append(exc)

        with patch('install.SOURCE', source), patch('install.architecture', return_value='arm64'), \
             patch('install.provision_app', return_value=(application, None)), \
             patch('install.validate_release', side_effect=validate):
            threads = [threading.Thread(target=run_install) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

        self.assertTrue(all(not thread.is_alive() for thread in threads), 'installer thread did not finish')
        self.assertEqual(errors, [])
        self.assertEqual(max_active_validations, 1)
        self.assertEqual((prefix / 'current/payload').read_text(), 'new version')
        self.assertEqual(len(list((prefix / 'releases').iterdir())), 3)

    def test_dependency_acquisition_failure_preserves_active_release(self):
        prefix = self.root / 'lcu'
        old = prefix / 'releases/old'
        old.mkdir(parents=True)
        (old / 'data').write_text('previous version')
        (prefix / '.lcu-install').touch()
        (prefix / 'current').symlink_to('releases/old')
        failure = subprocess.CalledProcessError(100, ['apt-get', 'install'])

        with patch('install.setup.validate', return_value=(None, [])), \
             patch('install.checked_prefix', return_value=prefix), \
             patch('install.architecture', return_value='arm64'), \
             patch('install.verify'), patch('install.preflight_app'), \
             patch('install.os.getuid', return_value=0), patch('install.shutil.which', return_value='/usr/bin/apt-get'), \
             patch('install.subprocess.run', side_effect=[None, failure]) as run, \
             patch('install.install', side_effect=AssertionError('release install reached')):
            with self.assertRaises(subprocess.CalledProcessError):
                install_main(['--prefix', str(prefix), '--runtime-only'])

        self.assertEqual(run.call_args_list[0].args[0], ['apt-get', 'update'])
        self.assertEqual(run.call_args_list[1].args[0][:3], ['apt-get', 'install', '-y'])
        self.assertEqual((prefix / 'current/data').read_text(), 'previous version')
        self.assertEqual(list((prefix / 'releases').iterdir()), [old])

    def test_unexpected_next_symlink_preserves_active_release(self):
        prefix = self.root / 'lcu'
        old = prefix / 'releases/old'
        old.mkdir(parents=True)
        (old / 'data').write_text('previous version')
        (prefix / '.lcu-install').touch()
        (prefix / 'current').symlink_to('releases/old')
        conflict = self.root / 'conflict'
        conflict.mkdir()
        (prefix / '.next').symlink_to(conflict, target_is_directory=True)
        source = self.root / 'bundle'
        source.mkdir()
        (source / 'payload').write_text('new version')
        (source / 'runtime.lock.json').write_text(json.dumps({
            'version': '26.915.31945', 'architectures': {'arm64': {'sha256': '0' * 64}}}))
        seal(source, 'arm64')
        application = self.root / 'chatgpt'
        application.mkdir()

        with patch('install.SOURCE', source), patch('install.architecture', return_value='arm64'), \
             patch('install.provision_app', return_value=(application, None)), \
             patch('install.validate_release'):
            with self.assertRaisesRegex(ValueError, 'Unexpected .next path'):
                install(prefix)

        self.assertEqual((prefix / 'current/data').read_text(), 'previous version')
        self.assertTrue((prefix / '.next').is_symlink())
        self.assertEqual(list((prefix / 'releases').iterdir()), [old])

    def test_caller_security_settings_survive(self):
        app = self.root / 'app'
        runtime = app / 'resources/cua_node'
        for path in (runtime / 'bin/node', runtime / 'bin/node_repl',
                     runtime / 'lib/node_modules/@oai/cua-repl/bin/cua-repl.mjs',
                     app / 'resources/codex', app / 'resources/codex-code-mode-host'):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
            path.chmod(0o755)
        (runtime / 'manifest.json').write_text('{"platform":"linux","arch":"arm64","runtime_archive_version":"runtime-pin"}')
        (app / 'resources/plugins/openai-bundled/plugins/chrome/.codex-plugin').mkdir(parents=True)
        (app / 'resources/plugins/openai-bundled/plugins/chrome/.codex-plugin/plugin.json').touch()
        (app / 'resources/plugins/openai-bundled/plugins/unified-computer-use').mkdir(parents=True)
        (app / 'resources/plugins/openai-bundled/plugins/unified-computer-use/.mcp.json').touch()
        (self.root / 'runtime.lock.json').write_text(json.dumps({
            'runtime': 'runtime-pin', 'version': '26.915.31945',
            'architectures': {'arm64': {'sha256': 'pinned-digest'}}}))
        (self.root / 'installation.json').write_text(json.dumps({
            'app': 'app', 'architecture': 'arm64',
            'package_version': '26.915.31945', 'sha256': 'pinned-digest'}))
        settings = {'NODE_REPL_FORCE_STRICT_AUTO_REVIEW': '1', 'NODE_REPL_ENFORCE_MODEL_CHECK': '1',
                    'CODEX_CLI_PATH': '/trusted/codex', 'NODE_REPL_ENABLE_NETWORK_ISOLATION': '1',
                    'NODE_REPL_JS_BANNER': 'configured startup', 'NODE_REPL_TRUSTED_SERVICES': 'configured services'}
        with patch.dict(os.environ, settings):
            result = environment(self.root)
        for key in settings:
            self.assertEqual(result[key], settings[key])
        self.assertEqual(result['CUA_REPL_ENABLED_SURFACES'], 'browser,computer')

    def session(self, pid, display=':1'):
        process = self.root / str(pid)
        process.mkdir()
        (process / 'comm').write_text('xfce4-session\n')
        (process / 'environ').write_bytes(f'DISPLAY={display}\0DBUS_SESSION_BUS_ADDRESS=unix:path=/run/test\0TOKEN=never-copy\0'.encode())

    def test_discovery_copies_only_gui_environment(self):
        self.session(123)
        self.assertEqual(discover(self.root), {'DISPLAY': ':1', 'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/run/test'})

    def test_ambiguous_desktop_is_rejected(self):
        self.session(123)
        self.session(124, ':2')
        with self.assertRaisesRegex(ValueError, 'found 2'):
            discover(self.root)

    def test_another_users_desktop_is_rejected(self):
        self.session(123)
        with self.assertRaisesRegex(ValueError, 'found 0'):
            discover(self.root, os.getuid() + 1)

    def test_concurrent_config_edit_is_preserved(self):
        path = self.root / 'config'
        path.write_bytes(b'concurrent change')
        with self.assertRaises(ValueError):
            apply_changes([Change(path, b'old config', b'new config')])
        self.assertEqual(path.read_bytes(), b'concurrent change')


if __name__ == '__main__':
    unittest.main()
