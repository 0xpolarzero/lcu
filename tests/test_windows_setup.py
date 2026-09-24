"""Windows setup selects the registered app's exact platform instructions."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from lcu import setup


class WindowsSetupTests(unittest.TestCase):
    def test_registered_windows_account_and_direct_session_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary).resolve()
            with mock.patch.object(setup.sys, 'platform', 'win32'), \
                 mock.patch.dict(os.environ, {'USERPROFILE': str(home)}, clear=False):
                args = setup.parser().parse_args(['--prefix', str(home / 'LCU'),
                                                   '--agent', 'codex', '--session', 'direct'])
                account, names = setup.validate(args)
                self.assertEqual((Path(account.pw_dir), names), (home, ['codex']))
                args.session = 'discover'
                with self.assertRaisesRegex(ValueError, 'direct'):
                    setup.validate(args)
                args.session = 'direct'
                args.export = home / 'export'
                with self.assertRaisesRegex(ValueError, 'Windows portable export'):
                    setup.validate(args)

    def test_windows_original_encoded_instruction_tree_copied_byte_exact(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            home = base / 'account'
            home.mkdir()
            release = base / 'release'
            release.mkdir()
            (release / 'installation.json').write_text(json.dumps({'platform': 'windows'}))
            resources = base / 'registered-msix/app/resources'
            modules = resources / 'cua_node/bin/node_modules/%40oai'
            original = b'Original Windows CUA guide \xc3\xa9\r\n'
            paths = [
                modules / 'cua/docs/tinysky-alt-core-cua-repl.md',
                modules / 'cua-repl/instructions/windows/description.md',
                modules / 'sky/docs/skills/oai_sky_lib/windows/SKILL.md',
                modules / 'sky/docs/sky-full-desktop-api.md',
                modules / 'sky/docs/sky-window-api.md',
                modules / 'sky/docs/sky-window2-api.md',
            ]
            for path in paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(original)
            source = Path(__file__).resolve().parents[1] / 'skills/lcu'
            with mock.patch.object(setup, 'installed_app_resources', return_value=resources):
                generated = setup.generate_skill(source, home, release)
            self.assertEqual((generated / 'references/upstream/cua-repl/instructions/windows/description.md').read_bytes(), original)
            self.assertEqual((generated / 'references/upstream/sky/windows/SKILL.md').read_bytes(), original)
            wrapper = (generated / 'SKILL.md').read_text()
            self.assertIn('original Windows computer-use guide', wrapper)
            self.assertNotIn('Chrome browser control', wrapper)
            self.assertFalse((generated / 'references/upstream/chrome').exists())


if __name__ == '__main__':
    unittest.main()
