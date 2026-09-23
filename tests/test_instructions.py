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
            '@oai/browser-desktop/environment-docs/codex-app/api.json': 'references/upstream/browser-desktop/codex-app/api.json',
            '@oai/browser-desktop/environment-docs/codex-app/documents.json': 'references/upstream/browser-desktop/codex-app/documents.json',
            '@oai/sky/docs/skills/oai_sky_lib/linux/SKILL.md': 'references/upstream/sky/linux/SKILL.md',
            '@oai/sky/docs/sky-full-desktop-api.md': 'references/upstream/sky/native-api.md',
            '@oai/sky/docs/sky-window-api.md': 'references/upstream/sky/window-api.md',
            '@oai/sky/docs/sky-window2-api.md': 'references/upstream/sky/window2-api.md',
            'plugins/openai-bundled/plugins/chrome/skills/control-chrome/SKILL.md': 'references/upstream/chrome/skill/SKILL.md',
            'plugins/openai-bundled/plugins/chrome/docs/capabilities/tab/cdp.md': 'references/upstream/chrome/docs/capabilities/tab/cdp.md',
        }
        for upstream, local in mapping.items():
            source = (self.resources / 'cua_node/lib/node_modules' / upstream
                      if upstream.startswith('@oai/') else self.resources / upstream)
            self.assertEqual((generated / local).read_bytes(), source.read_bytes())
        self.assertFalse((generated / 'references/upstream/cua-repl/instructions/macos').exists())
        self.assertIn('references/upstream/chrome/skill/SKILL.md', (generated / 'SKILL.md').read_text())

    def test_missing_instruction_source_does_not_replace_last_generated_skill(self):
        generated = generate_skill(self.skill_source, self.home, self.release)
        (generated / 'marker').write_text('previous generation')
        (self.modules / '@oai/sky/docs/sky-full-desktop-api.md').unlink()
        with self.assertRaisesRegex(ValueError, 'Original instruction file missing'):
            generate_skill(self.skill_source, self.home, self.release)
        self.assertEqual((generated / 'marker').read_text(), 'previous generation')

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

    def test_agent_registration_receives_local_pre_call_skill_with_copy(self):
        tool_root = self.root / 'agent-tools'
        tool_root.mkdir()
        node, skill_cli, mcp_cli = (tool_root / name for name in ('node', 'skills.mjs', 'mcp.mjs'))
        calls = []

        def run(argv, **kwargs):
            calls.append(argv)
            if argv[1:3] == [str(skill_cli), 'add']:
                source = Path(argv[3])
                self.assertTrue((source / 'references/upstream/cua/docs/tinysky-alt-core-cua-repl.md').is_file())
                self.assertTrue((source / 'references/upstream/chrome/skill/SKILL.md').is_file())
                self.assertIn('--copy', argv)
                return SimpleNamespace(returncode=0, stdout='[{"name":"lcu","status":"installed"}]')
            return SimpleNamespace(returncode=0, stdout='{}')

        with patch('lcu.setup.installer_paths', return_value=(node, skill_cli, mcp_cli)), \
                patch('lcu.setup.preflight_mcp'), patch('lcu.setup.subprocess.run', side_effect=run):
            failures = configure(['claude-code'], self.home, self.skill_source,
                                 ['/usr/bin/lcu'], tool_root, self.release,
                                 environ={'HOME': str(self.home)})
        self.assertEqual(failures, [])
        self.assertEqual(len(calls), 2)

    def test_selected_app_descriptor_and_resources_are_required(self):
        self.assertEqual(installed_app_resources(self.release), self.resources.resolve())
        self.assertEqual(host_policy(self.release), {'type': 'stdio'})
        (self.release / 'installation.json').unlink()
        with self.assertRaisesRegex(ValueError, 'descriptor missing'):
            installed_app_resources(self.release)

    def test_legacy_browser_host_flag_fails_with_chrome_migration(self):
        args = parser().parse_args(['--browser-host'])
        with self.assertRaisesRegex(ValueError, 'use the original Chrome provider'):
            validate(args)
