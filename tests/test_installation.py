import os
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import struct
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
from lcu.runtime import environment
from lcu.session import discover
from lcu.setup import Change, apply_changes, regular_path
from install import checked_prefix, install, main as install_main
from installed_app import (_cached_package, _check_package_identity, _validate_app,
                           _download, preflight as preflight_app, provision as provision_app,
                           _tree_inventory, _inventory_digest)
from bundle import seal


def _write_asar(path, members):
    files = {}
    payload = bytearray()
    for name, content in members.items():
        node = files
        parts = name.split('/')
        for part in parts[:-1]:
            node = node.setdefault(part, {'files': {}})['files']
        node[parts[-1]] = {'offset': str(len(payload)), 'size': len(content)}
        payload.extend(content)
    header = json.dumps({'files': files}, separators=(',', ':')).encode()
    path.write_bytes(struct.pack('<4I', 4, 8 + len(header), 4 + len(header), len(header)) +
                     header + payload)


def _application_fixture(root, *, version='26.924.22138', runtime_version='runtime-new',
                         arch='arm64', relocated=False):
    app = Path(root)
    resources = app / 'resources'
    runtime = resources / 'cua_node'
    executable = b'#!/bin/sh\nexit 0\n'
    for relative in ('ChatGPT', 'resources/cua_node/bin/node',
                     'resources/cua_node/bin/node_repl',
                     'resources/cua_node/lib/node_modules/@oai/cua-repl/bin/cua-repl.mjs'):
        path = app / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(executable if relative != 'resources/cua_node/lib/node_modules/@oai/cua-repl/bin/cua-repl.mjs' else b'export {};\n')
        if relative != 'resources/cua_node/lib/node_modules/@oai/cua-repl/bin/cua-repl.mjs':
            path.chmod(0o755)
    tools = resources / ('codex-cli/bin' if relocated else '')
    for name in ('codex', 'codex-code-mode-host'):
        path = tools / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(executable)
        path.chmod(0o755)
    (resources / 'app.asar').parent.mkdir(parents=True, exist_ok=True)
    _write_asar(resources / 'app.asar', {
        'package.json': json.dumps({'name': 'chatgpt', 'version': version}).encode()})
    (runtime / 'manifest.json').write_text(json.dumps({
        'platform': 'linux', 'arch': arch, 'runtime_archive_version': runtime_version}))
    (resources / 'plugins/openai-bundled/plugins/browser').mkdir(parents=True, exist_ok=True)
    for relative in (
        'plugins/openai-bundled/plugins/chrome/.codex-plugin/plugin.json',
        f'plugins/openai-bundled/plugins/chrome/extension-host/linux/{arch}/extension-host',
        'plugins/openai-bundled/plugins/unified-computer-use/.mcp.json',
        'plugins/openai-bundled/plugins/browser/install.js',
    ):
        path = resources / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(executable if relative.endswith('extension-host') else b'{}\n')
        if relative.endswith('extension-host'):
            path.chmod(0o755)
    return app


def _provisioned_generation(root, application):
    generation = Path(root) / 'apps' / ('26.924.22138-arm64-' + 'b' * 16)
    generation.mkdir(parents=True)
    (generation / 'installed.json').write_text(json.dumps({
        'package_version': '26.924.22138', 'runtime': 'runtime-new', 'architecture': 'arm64',
        'sha256': 'b' * 64, 'application': 'payload/usr/lib/chatgpt',
    }))
    return application, generation


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

    def test_missing_installed_app_fails_before_prefix_writes_or_download(self):
        prefix = self.root / 'lcu'
        lock = {'version': '26.915.31945', 'runtime': 'runtime-pin',
                'source': 'https://invalid/{deb_arch}.deb',
                'architectures': {'arm64': {'deb_arch': 'arm64', 'sha256': 'a' * 64}}}
        (self.root / 'runtime.lock.json').write_text(json.dumps(lock))
        missing = self.root / 'missing-chatgpt'
        for operation in (preflight_app, provision_app):
            with patch('installed_app.DEFAULT_APP_PATH', missing), \
                 patch('installed_app._download', side_effect=AssertionError('network reached')):
                with self.assertRaisesRegex(ValueError, 'chatgpt.com/download/'):
                    operation(prefix, 'arm64', offline=True, root=self.root)
            self.assertFalse(prefix.exists())

    def test_missing_installed_app_fails_before_apt_or_prefix_writes(self):
        prefix = self.root / 'lcu'
        missing = self.root / 'missing-chatgpt'
        with patch('installed_app.DEFAULT_APP_PATH', missing), \
             patch('install.setup.validate', return_value=(None, [])), \
             patch('install.architecture', return_value='arm64'), \
             patch('install.verify'), \
             patch('install.subprocess.run', side_effect=AssertionError('apt/network reached')):
            with self.assertRaisesRegex(ValueError, 'chatgpt.com/download/'):
                install_main(['--prefix', str(prefix), '--runtime-only', '--session', 'discover'])
        self.assertFalse(prefix.exists())

    def test_app_package_option_fails_with_existing_app_migration_before_writes(self):
        prefix = self.root / 'lcu'
        with patch('install.subprocess.run', side_effect=AssertionError('apt/network reached')):
            with self.assertRaisesRegex(ValueError, r'--app-package cannot install.*--existing-app PATH'):
                install_main(['--prefix', str(prefix), '--runtime-only', '--app-package',
                              str(self.root / 'chatgpt.deb')])
        self.assertFalse(prefix.exists())

    def test_linux_installer_forwards_audio_opt_in_to_agent_setup(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            home = base / 'account'
            home.mkdir()
            existing_app = base / 'chatgpt'
            existing_app.mkdir()
            account = SimpleNamespace(pw_name='fixture', pw_uid=1001, pw_dir=str(home))
            with patch('install.DEFAULT_APP_PATH', existing_app), \
                 patch('install.setup.validate', return_value=(account, ['pi'])), \
                 patch('install.architecture', return_value='arm64'), \
                 patch('install.verify'), patch('install.preflight_app'), \
                 patch('install.install'), patch('install.setup.installer_environment'), \
                 patch('install.subprocess.run') as run:
                install_main(['--prefix', str(base / 'lcu'), '--existing-app', str(existing_app),
                              '--agent', 'pi', '--audio', '--yes', '--skip-system'])
            command = run.call_args.args[0]
            self.assertIn('--audio', command)
            self.assertIn('--agent', command)
            self.assertIn('pi', command)

    def test_validated_package_cache_is_reused_offline_and_corruption_fails_closed(self):
        prefix = self.root / 'lcu'
        prefix.mkdir()
        source = self.root / 'official.deb'
        source.write_bytes(b'pinned package bytes')
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        lock = {'version': '26.915.31945'}
        entry = {'sha256': digest}
        with patch('installed_app._package_identity', return_value='26.915.31945'):
            cached = _cached_package(prefix, 'arm64', lock, entry, package=source)
            self.assertEqual(cached.read_bytes(), source.read_bytes())
            self.assertEqual(_cached_package(prefix, 'arm64', lock, entry, offline=True), cached)
        cached.write_bytes(b'corrupt cache')
        with patch('installed_app._package_identity', return_value='26.915.31945'), \
             self.assertRaisesRegex(ValueError, 'Cached application package is corrupt'):
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
        with patch('installed_app._package_identity', return_value=lock['version']):
            cached = _cached_package(prefix, 'arm64', lock, entry, package=source)
        self.assertEqual(cached.read_bytes(), source.read_bytes())
        self.assertFalse(stage.exists())
        cached.unlink()
        download = cache / ('.' + name + '.download')
        download.write_bytes(source.read_bytes())
        with patch('installed_app._download', side_effect=AssertionError('network used')), \
             patch('installed_app._package_identity', return_value=lock['version']):
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
        with patch('installed_app._package_identity',
                   side_effect=ValueError('Unexpected ChatGPT package identity')):
            with self.assertRaisesRegex(ValueError, 'Unexpected ChatGPT package identity'):
                provision_app(prefix, 'arm64', package=package, root=self.root)
        self.assertEqual(list((prefix / 'apps').iterdir()), [])

    def test_existing_app_accepts_its_actual_app_and_runtime_versions(self):
        app = _application_fixture(self.root / 'chatgpt', relocated=True)
        lock = {'version': '26.915.31945', 'runtime': 'runtime-pin',
                'architectures': {'arm64': {'sha256': 'a' * 64,
                                            'components': {'resources/app.asar': '0' * 64}}}}
        (self.root / 'runtime.lock.json').write_text(json.dumps(lock))
        application, generation = provision_app(
            self.root / 'lcu', 'arm64', existing_app=app, offline=True, root=self.root)
        installed = json.loads((generation / 'installed.json').read_text())
        self.assertEqual(application, generation / 'payload/usr/lib/chatgpt')
        self.assertEqual(installed['package_version'], '26.924.22138')
        self.assertEqual(installed['runtime'], 'runtime-new')
        self.assertEqual(installed['architecture'], 'arm64')
        self.assertEqual(installed['sha256'], _inventory_digest(_tree_inventory(application)))
        self.assertEqual(generation.name, f"26.924.22138-arm64-{installed['sha256'][:16]}")
        self.assertEqual(installed['package_sha256'], None)

    def test_missing_required_runtime_file_rejects_a_different_app_version(self):
        app = _application_fixture(self.root / 'chatgpt')
        (app / 'resources/cua_node/bin/node_repl').unlink()
        with self.assertRaisesRegex(ValueError, 'Application payload is incomplete'):
            _validate_app(app, 'arm64', execute=False)

    def test_managed_generation_inventory_drift_is_rejected(self):
        app = _application_fixture(self.root / 'chatgpt')
        lock = {'version': '26.915.31945', 'runtime': 'runtime-pin',
                'architectures': {'arm64': {'sha256': 'a' * 64}}}
        (self.root / 'runtime.lock.json').write_text(json.dumps(lock))
        prefix = self.root / 'lcu'
        _, generation = provision_app(prefix, 'arm64', existing_app=app, root=self.root)
        managed_app = generation / 'payload/usr/lib/chatgpt'
        (managed_app / 'resources/plugins/openai-bundled/plugins/browser/install.js').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'incomplete or corrupt'):
            preflight_app(prefix, 'arm64', existing_app=app, root=self.root)

    def test_local_package_uses_observed_version_runtime_and_content_identity(self):
        prefix = self.root / 'lcu'
        package = self.root / 'newer-chatgpt.deb'
        package.write_bytes(b'local package bytes unlike the pinned download')
        app = _application_fixture(self.root / 'package-app', version='26.924.22138',
                                   runtime_version='runtime-new', relocated=True)
        inventory = _tree_inventory(app)
        manifest = json.loads((app / 'resources/cua_node/manifest.json').read_text())
        lock = {'version': '26.915.31945', 'runtime': 'runtime-pin',
                'source': 'https://invalid/{deb_arch}',
                'architectures': {'arm64': {'deb_arch': 'arm64', 'sha256': 'a' * 64}}}
        (self.root / 'runtime.lock.json').write_text(json.dumps(lock))
        package_sha = hashlib.sha256(package.read_bytes()).hexdigest()
        real_run = subprocess.run

        def extract_selected(command, **options):
            if command[:2] == ['dpkg-deb', '--extract']:
                target = Path(command[3]) / 'usr/lib/chatgpt'
                target.parent.mkdir(parents=True)
                shutil.copytree(app, target, symlinks=True)
                return subprocess.CompletedProcess(command, 0)
            return real_run(command, **options)

        with patch('installed_app._package_identity', return_value='26.924.22138'), \
             patch('installed_app._package_inventory',
                   return_value=('26.924.22138', manifest, inventory)) as package_inventory, \
             patch('installed_app.subprocess.run', side_effect=extract_selected):
            preflight_app(prefix, 'arm64', package=package, root=self.root)
            application, generation = provision_app(prefix, 'arm64', package=package, root=self.root)
        installed = json.loads((generation / 'installed.json').read_text())
        self.assertEqual(installed['package_version'], '26.924.22138')
        self.assertEqual(installed['runtime'], 'runtime-new')
        self.assertEqual(installed['sha256'], _inventory_digest(inventory))
        self.assertEqual(installed['package_sha256'], package_sha)
        self.assertEqual(installed['source'], 'local-package')
        self.assertEqual(generation.name, f"26.924.22138-arm64-{installed['sha256'][:16]}")
        self.assertEqual(package_inventory.call_count, 2)
        with patch('installed_app._package_identity', return_value='26.924.22138'), \
             patch('installed_app._package_inventory', side_effect=AssertionError('re-extracted package')):
            reused_app, reused_generation = provision_app(
                prefix, 'arm64', package=package, offline=True, root=self.root)
        self.assertEqual(reused_app, application)
        self.assertEqual(reused_generation, generation)

    def test_offline_existing_app_does_not_require_an_unrelated_pinned_package(self):
        app = _application_fixture(self.root / 'chatgpt')
        lock = {'version': '26.915.31945', 'runtime': 'runtime-pin', 'source': 'unused',
                'architectures': {'arm64': {'deb_arch': 'arm64', 'sha256': 'a' * 64}}}
        (self.root / 'runtime.lock.json').write_text(json.dumps(lock))
        prefix = self.root / 'lcu'
        preflight_app(prefix, 'arm64', existing_app=app, offline=True, root=self.root)
        self.assertFalse((prefix / 'cache').exists())

    def test_dpkg_deb_labeled_identity_output_is_parsed_exactly(self):
        lock = {'version': '26.915.31945'}
        _check_package_identity(
            'Package: chatgpt\nVersion: 26.915.31945\nArchitecture: arm64\n', 'arm64', lock)
        with self.assertRaisesRegex(ValueError, 'Unexpected ChatGPT package identity'):
            _check_package_identity(
                'Package: unrelated\nVersion: 26.915.31945\nArchitecture: arm64\n', 'arm64', lock)

    def test_local_package_accepts_a_different_chatgpt_version(self):
        version = _check_package_identity(
            'Package: chatgpt\nVersion: 26.924.22138\nArchitecture: arm64\n', 'arm64')
        self.assertEqual(version, '26.924.22138')

    def test_package_version_cannot_escape_cache_or_generation_paths(self):
        with self.assertRaisesRegex(ValueError, 'unsafe path characters'):
            _check_package_identity(
                'Package: chatgpt\nVersion: ../../outside\nArchitecture: arm64\n', 'arm64')

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
        provided = _provisioned_generation(self.root, application)
        with patch('install.SOURCE', source), patch('install.architecture', return_value='arm64'), \
             patch('install.provision_app', return_value=provided), \
             patch('install.validate_release', side_effect=ValueError('runtime validation failed')):
            with self.assertRaisesRegex(ValueError, 'runtime validation failed'):
                install(prefix, existing_app=application)
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
        provided = _provisioned_generation(self.root, application)

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
                install(prefix, existing_app=application)
            except BaseException as exc:
                errors.append(exc)

        with patch('install.SOURCE', source), patch('install.architecture', return_value='arm64'), \
             patch('install.provision_app', return_value=provided), \
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
        existing_app = self.root / 'chatgpt'
        existing_app.mkdir()
        old = prefix / 'releases/old'
        old.mkdir(parents=True)
        (old / 'data').write_text('previous version')
        (prefix / '.lcu-install').touch()
        (prefix / 'current').symlink_to('releases/old')
        failure = subprocess.CalledProcessError(100, ['apt-get', 'install'])

        with patch('install.DEFAULT_APP_PATH', existing_app), \
             patch('install.setup.validate', return_value=(None, [])), \
             patch('install.checked_prefix', return_value=prefix), \
             patch('install.architecture', return_value='arm64'), \
             patch('install.verify'), patch('install.preflight_app'), \
             patch('install.os.getuid', return_value=0), patch('install.shutil.which', return_value='/usr/bin/apt-get'), \
             patch('install.subprocess.run', side_effect=[None, failure]) as run, \
             patch('install.install', side_effect=AssertionError('release install reached')):
            with self.assertRaises(subprocess.CalledProcessError):
                install_main(['--prefix', str(prefix), '--runtime-only', '--session', 'discover'])

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
        provided = _provisioned_generation(self.root, application)

        with patch('install.SOURCE', source), patch('install.architecture', return_value='arm64'), \
             patch('install.provision_app', return_value=provided), \
             patch('install.validate_release'):
            with self.assertRaisesRegex(ValueError, 'Unexpected .next path'):
                install(prefix, existing_app=application)

        self.assertEqual((prefix / 'current/data').read_text(), 'previous version')
        self.assertTrue((prefix / '.next').is_symlink())
        self.assertEqual(list((prefix / 'releases').iterdir()), [old])

    def test_caller_security_settings_survive(self):
        source_app = _application_fixture(self.root / 'source-app')
        inventory = _tree_inventory(source_app)
        digest = _inventory_digest(inventory)
        version = '26.924.22138'
        generation = self.root / 'apps' / f'{version}-arm64-{digest[:16]}'
        app = generation / 'payload/usr/lib/chatgpt'
        app.parent.mkdir(parents=True)
        shutil.copytree(source_app, app, symlinks=True)
        (generation / 'installed.json').write_text(json.dumps({
            'package_version': version, 'runtime': 'runtime-new', 'architecture': 'arm64',
            'sha256': digest, 'application': 'payload/usr/lib/chatgpt', 'inventory': inventory,
        }))
        (self.root / 'app').symlink_to(os.path.relpath(app, self.root), target_is_directory=True)
        (self.root / 'runtime.lock.json').write_text(json.dumps({
            'runtime': 'runtime-pin', 'version': '26.915.31945',
            'architectures': {'arm64': {'sha256': 'pinned-digest'}}}))
        (self.root / 'installation.json').write_text(json.dumps({
            'app': 'app', 'architecture': 'arm64',
            'package_version': version, 'runtime': 'runtime-new', 'sha256': digest}))
        settings = {'NODE_REPL_FORCE_STRICT_AUTO_REVIEW': '1', 'NODE_REPL_ENFORCE_MODEL_CHECK': '1',
                    'CODEX_CLI_PATH': '/trusted/codex', 'NODE_REPL_ENABLE_NETWORK_ISOLATION': '1',
                    'NODE_REPL_JS_BANNER': 'configured startup', 'NODE_REPL_TRUSTED_SERVICES': 'configured services'}
        with patch.dict(os.environ, settings):
            result = environment(self.root)
        for key in settings:
            self.assertEqual(result[key], settings[key])
        self.assertEqual(result['CUA_REPL_ENABLED_SURFACES'], 'computer')

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
