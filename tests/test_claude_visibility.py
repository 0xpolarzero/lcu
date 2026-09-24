import json
from pathlib import Path
import tempfile
import unittest

from lcu.claude_visibility import HOST_ONLY, install


class ClaudeVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve())
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name) / 'home'
        self.home.mkdir()

    def test_user_scope_preserves_unrelated_settings_and_is_idempotent(self):
        path = self.home / '.claude/settings.json'
        path.parent.mkdir()
        path.write_text('{"model":"sonnet","permissions":{"allow":["Read"],"deny":["Bash(rm *)"]}}\n')
        self.assertEqual(install(self.home), path)
        data = json.loads(path.read_text())
        self.assertEqual(data['model'], 'sonnet')
        self.assertEqual(data['permissions']['allow'], ['Read'])
        self.assertEqual(data['permissions']['deny'], ['Bash(rm *)', *HOST_ONLY])
        first = path.read_bytes()
        install(self.home)
        self.assertEqual(path.read_bytes(), first)

    def test_project_scope_writes_local_file_only(self):
        project = self.home / 'project'
        project.mkdir()
        path = install(self.home, project=project)
        self.assertEqual(path, project / '.claude/settings.local.json')
        self.assertEqual(json.loads(path.read_text())['permissions']['deny'], list(HOST_ONLY))
        self.assertFalse((self.home / '.claude/settings.json').exists())
        self.assertFalse((project / '.claude/settings.json').exists())

    def test_malformed_existing_settings_remain_unchanged(self):
        path = self.home / '.claude/settings.json'
        path.parent.mkdir()
        path.write_bytes(b'{broken JSON')
        with self.assertRaises(json.JSONDecodeError):
            install(self.home)
        self.assertEqual(path.read_bytes(), b'{broken JSON')


if __name__ == '__main__':
    unittest.main()
