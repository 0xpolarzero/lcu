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
        path.write_text(json.dumps({
            'model': 'sonnet',
            'permissions': {'allow': ['Read'], 'deny': ['Bash(rm *)']},
            'hooks': {'UserPromptSubmit': [{'hooks': [{'type': 'command', 'command': 'existing-hook'}]}]},
        }) + '\n')
        self.assertEqual(install(self.home), path)
        data = json.loads(path.read_text())
        self.assertEqual(data['model'], 'sonnet')
        self.assertEqual(data['permissions']['allow'], ['Read'])
        self.assertEqual(data['permissions']['deny'], ['Bash(rm *)', *HOST_ONLY])
        self.assertEqual(data['hooks']['UserPromptSubmit'][0]['hooks'][0]['command'], 'existing-hook')
        before_context = [hook for group in data['hooks']['PreToolUse'] for hook in group['hooks']
                          if hook.get('tool') == 'set_turn_context']
        self.assertEqual(len(before_context), 1)
        self.assertEqual(before_context[0]['type'], 'mcp_tool')
        self.assertEqual(before_context[0]['input']['turn_id'], '${prompt_id}')
        stop_cleanup = [hook for group in data['hooks']['Stop'] for hook in group['hooks']
                        if hook.get('tool') == 'turn_ended']
        self.assertEqual(len(stop_cleanup), 1)
        self.assertEqual(stop_cleanup[0]['input']['turn_id'], '${prompt_id}')
        failure_cleanup = [hook for group in data['hooks']['StopFailure'] for hook in group['hooks']
                           if hook.get('tool') == 'turn_ended']
        self.assertEqual(len(failure_cleanup), 1)
        self.assertEqual(failure_cleanup[0]['input']['hook_event_name'], 'Interrupt')
        first = path.read_bytes()
        install(self.home)
        self.assertEqual(path.read_bytes(), first)

    def test_existing_hook_groups_are_preserved_and_malformed_hooks_are_refused(self):
        path = self.home / '.claude/settings.json'
        path.parent.mkdir()
        context_hook = {
            'type': 'mcp_tool', 'server': 'lcu', 'tool': 'set_turn_context',
            'input': {
                'session_id': '${session_id}', 'turn_id': '${prompt_id}',
                'tool_use_id': '${tool_use_id}', 'agent_id': '${agent_id}',
            },
        }
        path.write_text(json.dumps({'hooks': {
            'PreToolUse': [{'matcher': 'Bash', 'hooks': [context_hook]}],
            'Stop': [{'hooks': [{'type': 'command', 'command': 'existing-stop'}]}],
        }}))
        install(self.home)
        data = json.loads(path.read_text())
        self.assertEqual(data['hooks']['PreToolUse'][0]['matcher'], 'Bash')
        self.assertEqual(data['hooks']['PreToolUse'][0]['hooks'][0], context_hook)
        self.assertEqual(data['hooks']['Stop'][0]['hooks'][0]['command'], 'existing-stop')
        self.assertEqual(len(data['hooks']['PreToolUse']), 2)
        self.assertEqual(len(data['hooks']['Stop']), 2)

        path.write_text('{"hooks":[]}')
        malformed = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'hooks must be an object'):
            install(self.home)
        self.assertEqual(path.read_bytes(), malformed)

    def test_malformed_nested_hook_structures_are_refused_without_writes(self):
        path = self.home / '.claude/settings.json'
        path.parent.mkdir()
        malformed_values = [
            {'hooks': {'PreToolUse': {}}},
            {'hooks': {'PreToolUse': [{'matcher': 'Bash', 'hooks': {}}]}},
            {'hooks': {'Stop': [{'hooks': [None]}]}},
        ]
        for value in malformed_values:
            with self.subTest(value=value):
                original = (json.dumps(value) + '\n').encode()
                path.write_bytes(original)
                with self.assertRaises(ValueError):
                    install(self.home)
                self.assertEqual(path.read_bytes(), original)

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
