import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lcu.setup import configure, export_bundle, generate_skill, host_policy, installed_app_resources, parser, validate
from lcu.setup_clients import CLIENTS

class InstalledInstructionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve())
        self.root = Path(self.temp.name)
        self.release = self.root / 'release'
        self.app = self.release / 'app'
        self.resources = self.app / 'resources'
        self.modules = self.resources / 'cua_node/lib/node_modules'
        self.home = self.root / 'home'
        self.home.mkdir()
        self.release.mkdir()
        (self.release / 'installation.json').write_text('{"version":"fixture","app":"app"}')
        host_plugin = self.resources / 'plugins/openai-bundled/plugins/unified-computer-use'
        host_plugin.mkdir(parents=True)
        (host_plugin / '.mcp.json').write_text('{"mcpServers":{"cua_repl":{"type":"stdio","command":"node","args":[]}}}')
        required = {
            '@oai/cua/docs/tinysky-alt-core-cua-repl.md': 'original core guide',
            '@oai/cua/docs/tinysky-alt-confirmations.md': 'original policy guide',
            '@oai/cua-repl/instructions/linux/description.md': 'original Linux description',
            '@oai/cua-repl/instructions/linux/computer.md': 'original Linux computer docs',
            '@oai/cua-repl/instructions/macos/description.md': 'inactive macOS description',
            '@oai/browser-desktop/environment-docs/codex-app/api.json': '{"api":[]}',
            '@oai/browser-desktop/environment-docs/codex-app/documents.json': '{"documents":[]}',
            '@oai/browser-desktop/environment-docs/codex-app/capabilities/tab/cdp.md': 'effective Chrome docs',
            '@oai/sky/docs/skills/oai_sky_lib/linux/SKILL.md': 'original Linux skill',
            '@oai/sky/docs/sky-full-desktop-api.md': 'original native API',
            '@oai/sky/docs/sky-window-api.md': 'original window API',
            '@oai/sky/docs/sky-window2-api.md': 'original window API version two',
        }
        for relative, text in required.items():
            path = self.modules / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        chrome = self.resources / 'plugins/openai-bundled/plugins/chrome'
        for relative, text in {
            'docs/api.json': '{"apis":[]}',
            'docs/documents.json': '{"documents":[]}',
            'docs/capabilities/tab/cdp.md': 'original Chrome capability',
            'skills/control-chrome/SKILL.md': 'original Chrome skill',
        }.items():
            path = chrome / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        self.skill_source = self.root / 'skill-source'
        self.skill_source.mkdir()
        (self.skill_source / 'SKILL.md').write_bytes(
            (Path(__file__).resolve().parents[1] / 'skills/lcu/SKILL.md').read_bytes())

    def tearDown(self):
        self.temp.cleanup()

    def test_generated_skill_has_complete_pre_call_sources_byte_identically(self):
        generated = generate_skill(self.skill_source, self.home, self.release)
        self.assertEqual((generated / 'SKILL.md').read_bytes(), (self.skill_source / 'SKILL.md').read_bytes())
        mapping = {
            '@oai/cua/docs/tinysky-alt-core-cua-repl.md': 'references/upstream/cua/docs/tinysky-alt-core-cua-repl.md',
            '@oai/cua-repl/instructions/linux/description.md': 'references/upstream/cua-repl/instructions/linux/description.md',
            '@oai/sky/docs/skills/oai_sky_lib/linux/SKILL.md': 'references/upstream/sky/linux/SKILL.md',
            '@oai/sky/docs/sky-full-desktop-api.md': 'references/upstream/sky/native-api.md',
            '@oai/sky/docs/sky-window-api.md': 'references/upstream/sky/window-api.md',
            '@oai/sky/docs/sky-window2-api.md': 'references/upstream/sky/window2-api.md',
        }
        for upstream, local in mapping.items():
            source = (self.resources / 'cua_node/lib/node_modules' / upstream
                      if upstream.startswith('@oai/') else self.resources / upstream)
            self.assertEqual((generated / local).read_bytes(), source.read_bytes())
        self.assertFalse((generated / 'references/upstream/cua-repl/instructions/macos').exists())
        self.assertFalse((generated / 'references/upstream/browser-desktop').exists())
        self.assertFalse((generated / 'references/upstream/chrome').exists())
        self.assertNotIn('Chrome', (generated / 'SKILL.md').read_text())

    def test_chrome_opt_in_retains_original_browser_and_plugin_guides(self):
        generated = generate_skill(self.skill_source, self.home, self.release, chrome=True)
        self.assertEqual((generated / 'references/upstream/browser-desktop/codex-app/api.json').read_bytes(),
                         (self.modules / '@oai/browser-desktop/environment-docs/codex-app/api.json').read_bytes())
        self.assertEqual((generated / 'references/upstream/browser-desktop/codex-app/documents.json').read_bytes(),
                         (self.modules / '@oai/browser-desktop/environment-docs/codex-app/documents.json').read_bytes())
        self.assertEqual((generated / 'references/upstream/chrome/docs/documents.json').read_bytes(),
                         (self.resources / 'plugins/openai-bundled/plugins/chrome/docs/documents.json').read_bytes())
        self.assertEqual((generated / 'references/upstream/chrome/skill/SKILL.md').read_bytes(),
                         (self.resources / 'plugins/openai-bundled/plugins/chrome/skills/control-chrome/SKILL.md').read_bytes())
        self.assertIn('references/upstream/browser-desktop/codex-app/api.json',
                      (generated / 'SKILL.md').read_text())
        self.assertIn('description: Control Linux desktop windows and opted-in Chrome tabs',
                      (generated / 'SKILL.md').read_text())
        self.assertIn('entrypoints do not apply to LCU', (generated / 'SKILL.md').read_text())

    def test_missing_instruction_source_does_not_replace_last_generated_skill(self):
        generated = generate_skill(self.skill_source, self.home, self.release)
        (generated / 'marker').write_text('previous generation')
        (self.modules / '@oai/sky/docs/sky-full-desktop-api.md').unlink()
        with self.assertRaisesRegex(ValueError, 'Original instruction file missing'):
            generate_skill(self.skill_source, self.home, self.release)
        self.assertEqual((generated / 'marker').read_text(), 'previous generation')

    def test_macos_skill_selects_original_macos_guides_without_linux_guidance(self):
        # A macOS bundle has a different resources root, but its original guides
        # must be copied exactly as Linux guides are, never translated or edited.
        contents = self.app / 'Contents'
        contents.mkdir()
        self.resources.rename(contents / 'Resources')
        self.resources = contents / 'Resources'
        self.modules = self.resources / 'cua_node/lib/node_modules'
        (self.release / 'installation.json').write_text(
            '{"platform":"darwin","app":"app"}')
        sky = self.modules / '@oai/sky/docs/skills/oai_sky_lib/macos/SKILL.md'
        sky.parent.mkdir(parents=True)
        sky.write_bytes(b'complete original macOS guide\n')
        generated = generate_skill(self.skill_source, self.home, self.release)
        self.assertEqual(installed_app_resources(self.release), self.resources.resolve())
        self.assertEqual((generated / 'references/upstream/sky/macos/SKILL.md').read_bytes(),
                         sky.read_bytes())
        self.assertEqual((generated / 'references/upstream/cua-repl/instructions/macos/description.md').read_bytes(),
                         (self.modules / '@oai/cua-repl/instructions/macos/description.md').read_bytes())
        self.assertFalse((generated / 'references/upstream/cua-repl/instructions/linux').exists())
        wrapper = (generated / 'SKILL.md').read_text()
        self.assertIn('references/upstream/sky/macos/SKILL.md', wrapper)
        self.assertNotIn('Linux', wrapper)
        self.assertNotIn('instructions/linux', wrapper)
        chrome_skill = generate_skill(self.skill_source, self.home, self.release, chrome=True)
        self.assertIn('description: Control macOS desktop windows and opted-in Chrome tabs',
                      (chrome_skill / 'SKILL.md').read_text())

    def test_export_contains_only_lcu_authored_bootstrap_not_upstream_payload(self):
        destination = self.root / 'export'
        with patch('lcu.setup.host_policy', return_value={}), patch('lcu.codex_hooks.export_files', return_value={}):
            export_bundle(destination, self.skill_source, ['/usr/bin/lcu'], self.release)
        contents = b'\n'.join(path.read_bytes() for path in destination.rglob('*') if path.is_file())
        self.assertIn(b'run `lcu setup', contents)
        self.assertNotIn(b'original core guide', contents)
        self.assertNotIn(b'original Chrome skill', contents)
        self.assertNotIn(str(self.root).encode(), contents)
        self.assertNotIn(b'/usr/bin/lcu', contents)
        command = json.loads((destination / 'mcp.json').read_text())['mcpServers']['lcu']
        self.assertEqual(command['command'], '/bin/sh')
        self.assertIn('LCU_PREFIX', command['args'][1])
        self.assertIn('LCU_SESSION_MODE', command['args'][1])

    def test_chrome_export_marks_original_reference_sources_without_copying_them(self):
        destination = self.root / 'export-chrome'
        with patch('lcu.setup.host_policy', return_value={}), patch('lcu.codex_hooks.export_files', return_value={}):
            export_bundle(destination, self.skill_source, ['/usr/bin/lcu'], self.release, chrome=True)
        command = json.loads((destination / 'mcp.json').read_text())['mcpServers']['lcu']
        self.assertEqual(command['args'][-1], '--chrome')
        metadata = json.loads((destination / 'lcu-bootstrap.json').read_text())
        self.assertTrue(any('/plugins/chrome/skills/control-chrome' in item for item in metadata['instructionSources']))
        self.assertFalse((destination / 'skills/lcu/references').exists())

    def test_exported_command_resolves_destination_prefix_and_session(self):
        destination = self.root / 'export'
        with patch('lcu.setup.host_policy', return_value={}), patch('lcu.codex_hooks.export_files', return_value={}):
            export_bundle(destination, self.skill_source, ['/producer/private/lcu'], self.release)
        command = json.loads((destination / 'mcp.json').read_text())['mcpServers']['lcu']
        prefix = self.root / 'destination'
        bin_dir = prefix / 'current/bin'
        bin_dir.mkdir(parents=True)
        for name in ('lcu', 'lcu-session'):
            script = bin_dir / name
            script.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
            script.chmod(0o755)
        env = {**os.environ, 'LCU_PREFIX': str(prefix), 'LCU_SESSION_MODE': 'direct'}
        result = subprocess.run([command['command'], *command['args'], 'doctor'],
                                env=env, text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout, 'doctor\n')
        env['LCU_SESSION_MODE'] = 'discover'
        result = subprocess.run([command['command'], *command['args'], 'doctor'],
                                env=env, text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout, f'--user\n{pwd.getpwuid(os.getuid()).pw_name}\n--\n{bin_dir / "lcu"}\ndoctor\n')

    def test_claude_setup_forwards_command_and_installs_host_visibility_hooks(self):
        tool_root = self.root / 'agent-tools'
        tool_root.mkdir()
        node, skill_cli, mcp_cli = (tool_root / name for name in ('node', 'skills.mjs', 'mcp.mjs'))
        adapter = self.release / 'adapters/claude.mjs'
        adapter.parent.mkdir(parents=True)
        adapter.write_text('fixture relay')
        project = self.root / 'project'
        project.mkdir()
        user_settings = self.home / '.claude/settings.json'
        user_settings.parent.mkdir()
        user_settings.write_text(json.dumps({
            'model': 'sonnet',
            'permissions': {'allow': ['Read'], 'deny': ['Bash(rm *)']},
            'hooks': {'UserPromptSubmit': [{'hooks': [{'type': 'command', 'command': 'keep-me'}]}]},
        }))
        calls = []
        selected_chrome = {'value': False}

        def run(argv, **kwargs):
            calls.append(argv)
            if argv[1:3] == [str(skill_cli), 'add']:
                source = Path(argv[3])
                self.assertTrue((source / 'references/upstream/cua/docs/tinysky-alt-core-cua-repl.md').is_file())
                self.assertEqual((source / 'references/upstream/browser-desktop').exists(),
                                 selected_chrome['value'])
                self.assertEqual((source / 'references/upstream/chrome').exists(),
                                 selected_chrome['value'])
                self.assertIn('--copy', argv)
                return SimpleNamespace(returncode=0, stdout='[{"name":"lcu","status":"installed"}]')
            return SimpleNamespace(returncode=0, stdout='{}')

        def register(scope, command, *, chrome=False):
            calls.clear()
            selected_chrome['value'] = chrome
            with patch('lcu.setup.installer_paths', return_value=(node, skill_cli, mcp_cli)), \
                    patch('lcu.setup.preflight_mcp'), patch('lcu.setup.subprocess.run', side_effect=run):
                failures = configure(['claude-code'], self.home, self.skill_source,
                                     command, tool_root, self.release, scope=scope,
                                     project=project if scope == 'project' else None,
                                     chrome=chrome, environ={'HOME': str(self.home)})
            self.assertEqual(failures, [])
            self.assertEqual(len(calls), 2)
            mcp_call = next(argv for argv in calls if argv[1:3] == ['--input-type=module', '-e'])
            self.assertEqual(mcp_call[4], str(mcp_cli))
            self.assertEqual(mcp_call[5:7], ['claude-code', scope])
            return json.loads(mcp_call[-2])

        base_command = ['/usr/bin/lcu', '--session', 'direct']
        self.assertEqual(register('user', base_command), [str(node), str(adapter), *base_command])
        configured_user = user_settings.read_bytes()
        user_data = json.loads(configured_user)
        self.assertEqual(user_data['model'], 'sonnet')
        self.assertEqual(user_data['permissions']['allow'], ['Read'])
        self.assertEqual(user_data['permissions']['deny'], ['Bash(rm *)',
                         'mcp__lcu__turn_ended', 'mcp__lcu__js_add_node_module_dir',
                         'mcp__lcu__set_turn_context'])
        self.assertEqual(user_data['hooks']['UserPromptSubmit'][0]['hooks'][0]['command'], 'keep-me')
        self.assertEqual(user_data['hooks']['PreToolUse'][0]['matcher'],
                         'mcp__lcu__js|mcp__lcu__js_reset')
        context_hook = user_data['hooks']['PreToolUse'][0]['hooks'][0]
        self.assertEqual((context_hook['type'], context_hook['server'], context_hook['tool']),
                         ('mcp_tool', 'lcu', 'set_turn_context'))
        self.assertEqual(context_hook['input']['session_id'], '${session_id}')
        self.assertEqual(context_hook['input']['turn_id'], '${prompt_id}')
        self.assertEqual(context_hook['input']['tool_use_id'], '${tool_use_id}')
        cleanup_hook = user_data['hooks']['Stop'][0]['hooks'][0]
        self.assertEqual((cleanup_hook['type'], cleanup_hook['server'], cleanup_hook['tool']),
                         ('mcp_tool', 'lcu', 'turn_ended'))
        self.assertEqual(cleanup_hook['input']['session_id'], '${session_id}')
        self.assertEqual(cleanup_hook['input']['turn_id'], '${prompt_id}')
        register('user', base_command)
        self.assertEqual(user_settings.read_bytes(), configured_user)

        project_command = [*base_command, '--chrome']
        self.assertEqual(register('project', project_command, chrome=True),
                         [str(node), str(adapter), *project_command])
        project_settings = project / '.claude/settings.local.json'
        self.assertTrue(project_settings.is_file())
        self.assertFalse((project / '.claude/settings.json').exists())
        self.assertEqual(json.loads(project_settings.read_text())['permissions']['deny'], [
            'mcp__lcu__turn_ended', 'mcp__lcu__js_add_node_module_dir',
            'mcp__lcu__set_turn_context'])
        configured_project = project_settings.read_bytes()
        register('project', project_command, chrome=True)
        self.assertEqual(project_settings.read_bytes(), configured_project)
        self.assertEqual(user_settings.read_bytes(), configured_user)

    def test_pi_registration_uses_original_skill_and_offline_local_package(self):
        self.assertEqual(set(CLIENTS), {'codex', 'claude-code', 'pi'})
        tool_root = self.root / 'agent-tools'
        node, skill_cli, mcp_cli = (tool_root / name for name in ('node', 'skills.mjs', 'mcp.mjs'))
        (self.release / 'adapters/pi').mkdir(parents=True)
        (self.release / 'adapters/pi/index.ts').write_text('fixture')
        calls = []

        def run(argv, **kwargs):
            calls.append((argv, kwargs))
            if argv[1:3] == [str(skill_cli), 'add']:
                self.assertIn('--agent', argv)
                self.assertEqual(argv[argv.index('--agent') + 1], 'pi')
                self.assertIn('--copy', argv)
                return SimpleNamespace(returncode=0, stdout='[{"name":"lcu","status":"installed"}]')
            self.assertEqual(argv[1:3], ['install', str(self.home / '.local/share/lcu/pi/extension.mjs')])
            self.assertEqual(kwargs['env']['PI_OFFLINE'], '1')
            return SimpleNamespace(returncode=0, stdout='Installed')

        with patch('lcu.setup.installer_paths', return_value=(node, skill_cli, mcp_cli)), \
                patch('lcu.setup.shutil.which', return_value='/bin/pi'), \
                patch('lcu.setup.subprocess.run', side_effect=run):
            failures = configure(['pi'], self.home, self.skill_source,
                                 ['/usr/bin/lcu'], tool_root, self.release,
                                 environ={'HOME': str(self.home)})
        self.assertEqual(failures, [])
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][0][0], '/bin/pi')
        wrapper = (self.home / '.local/share/lcu/pi/extension.mjs').read_text()
        self.assertIn((self.release / 'adapters/pi/index.ts').as_uri(), wrapper)
        self.assertIn('realpathSync(process.cwd())', wrapper)
        self.assertNotIn('.pi/lcu-command.json', wrapper)
        self.assertEqual(json.loads((self.home / '.local/share/lcu/pi/commands.json').read_text()),
                         {'projects': {}, 'user': ['/usr/bin/lcu']})

    def test_selected_app_descriptor_and_resources_are_required(self):
        self.assertEqual(installed_app_resources(self.release), self.resources.resolve())
        self.assertEqual(host_policy(self.release), {'type': 'stdio'})
        (self.release / 'installation.json').unlink()
        with self.assertRaisesRegex(ValueError, 'descriptor missing'):
            installed_app_resources(self.release)

    def test_legacy_browser_host_flag_fails_with_chrome_migration(self):
        args = parser().parse_args(['--browser-host'])
        with self.assertRaisesRegex(ValueError, 'setup --agent AGENT --chrome'):
            validate(args)

    def test_chrome_export_only_adds_runtime_flag_when_selected(self):
        with patch('lcu.setup.host_policy', return_value={}), patch('lcu.codex_hooks.export_files', return_value={}):
            export_bundle(self.root / 'native-export', self.skill_source, ['/usr/bin/lcu'], self.release)
            export_bundle(self.root / 'chrome-export', self.skill_source, ['/usr/bin/lcu', '--chrome'],
                          self.release, chrome=True)
        native = json.loads((self.root / 'native-export/mcp.json').read_text())['mcpServers']['lcu']
        browser = json.loads((self.root / 'chrome-export/mcp.json').read_text())['mcpServers']['lcu']
        self.assertNotIn('--chrome', native['args'])
        self.assertEqual(browser['args'][-1], '--chrome')
        metadata = json.loads((self.root / 'chrome-export/lcu-bootstrap.json').read_text())
        self.assertIn('--chrome', metadata['destinationSetup'])
