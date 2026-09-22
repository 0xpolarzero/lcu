import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
from cual.runtime import environment
from cual.session import discover
from cual.setup import Change, apply_changes, regular_path
from install import checked_prefix, install
from project_runtime import download, remove_arm, replace


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
            checked_prefix(self.root / 'link/cual')

    def test_relative_prefix_is_rejected(self):
        with self.assertRaises(ValueError):
            checked_prefix(Path('relative/cual'))

    def test_corrupt_download_never_executes(self):
        source = self.root / 'source'
        source.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'Integrity'):
            download(source.as_uri(), self.root / 'download', '0' * 64)

    def test_failed_upgrade_preserves_active_release(self):
        prefix = self.root / 'cual'
        old = prefix / 'releases/old'
        old.mkdir(parents=True)
        (old / 'data').write_text('previous version')
        (prefix / '.cual-install').touch()
        (prefix / 'current').symlink_to('releases/old')
        with patch('install.provision', side_effect=ValueError('bad upstream hash')):
            with self.assertRaisesRegex(ValueError, 'bad upstream'):
                install(prefix)
        self.assertEqual((prefix / 'current/data').read_text(), 'previous version')
        self.assertEqual(list((prefix / 'releases').iterdir()), [old])
        self.assertFalse(list(prefix.glob('.build-*')))

    def test_caller_security_settings_survive(self):
        settings = {'NODE_REPL_FORCE_STRICT_AUTO_REVIEW': '1', 'NODE_REPL_ENFORCE_MODEL_CHECK': '1',
                    'CODEX_CLI_PATH': '/trusted/codex', 'NODE_REPL_ENABLE_NETWORK_ISOLATION': '1',
                    'NODE_REPL_JS_BANNER': 'unwanted code', 'NODE_REPL_TRUSTED_SERVICES': 'wrong runtime'}
        with patch.dict(os.environ, settings):
            result = environment(self.root)
        for key in list(settings)[:4]:
            self.assertEqual(result[key], settings[key])
        self.assertNotIn('NODE_REPL_JS_BANNER', result)
        self.assertNotIn('NODE_REPL_TRUSTED_SERVICES', result)
        self.assertEqual(result['CUA_REPL_ENABLED_SURFACES'], 'computer')

    def test_source_drift_fails_closed(self):
        path = self.root / 'source.js'
        path.write_text('unexpected upstream')
        with self.assertRaises(ValueError):
            replace(path, 'old code', 'new code')
        self.assertEqual(path.read_text(), 'unexpected upstream')

    def test_dispatch_reordering_fails_closed(self):
        path = self.root / 'source.js'
        path.write_text('end;start;')
        with self.assertRaises(ValueError):
            remove_arm(path, 'start;', 'end;')
        self.assertEqual(path.read_text(), 'end;start;')

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
