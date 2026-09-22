import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from bundle import seal, verify


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'bundle'
        (self.root / 'runtime/bin').mkdir(parents=True)
        self.binary = self.root / 'runtime/bin/node'
        self.binary.write_bytes(b'fixture binary')
        self.binary.chmod(0o755)
        (self.root / 'runtime/bin/alias').symlink_to('node')
        seal(self.root, 'arm64')

    def test_relocated_bundle_verifies(self):
        moved = self.root.with_name('moved')
        self.root.rename(moved)
        verify(moved, 'arm64')

    def test_modified_file_is_rejected(self):
        self.binary.write_bytes(b'corrupted binary')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            verify(self.root, 'arm64')

    def test_missing_file_is_rejected(self):
        self.binary.unlink()
        with self.assertRaises(ValueError):
            verify(self.root, 'arm64')

    def test_injected_module_is_rejected(self):
        (self.root / 'runtime/unexpected.js').write_text('unexpected code')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            verify(self.root, 'arm64')

    def test_wrong_architecture_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'architecture'):
            verify(self.root, 'x64')

    def test_invalid_manifest_shape_is_rejected(self):
        (self.root / 'bundle.json').write_text('[]')
        with self.assertRaisesRegex(ValueError, 'manifest'):
            verify(self.root, 'arm64')

    def test_missing_payload_does_not_download(self):
        (self.root / 'bundle.json').unlink()
        with self.assertRaisesRegex(ValueError, 'release bundle'):
            verify(self.root, 'arm64')

    def test_escaping_symlink_is_rejected(self):
        alias = self.root / 'runtime/bin/alias'
        alias.unlink()
        alias.symlink_to('/bin/sh')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            verify(self.root, 'arm64')

    def test_executable_bit_change_is_rejected(self):
        self.binary.chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'integrity'):
            verify(self.root, 'arm64')
