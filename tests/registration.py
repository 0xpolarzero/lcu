"""Run as root in the disposable container; inspect another account's outputs."""
import json
import os
from pathlib import Path
import pwd
import subprocess
import tomllib

prefix = Path('/opt/lcu')
command = str(prefix / 'current/bin/lcu')
account = 'lcutester'
try:
    owner = pwd.getpwnam(account)
except KeyError:
    subprocess.run(['useradd', '--create-home', account], check=True)
    owner = pwd.getpwnam(account)
home = Path(owner.pw_dir)
project = home / 'project'
project.mkdir(exist_ok=True)
os.chown(project, owner.pw_uid, owner.pw_gid)
# The upstream formatter can rewrite comments; configuration values must survive.
codex = home / '.codex/config.toml'
codex.parent.mkdir(exist_ok=True)
os.chown(codex.parent, owner.pw_uid, owner.pw_gid)
codex.write_text('# keep my settings\nmodel = "my-model"\n[mcp_servers.other]\ncommand = "keep-me"\n')
os.chown(codex, owner.pw_uid, owner.pw_gid)
claude_settings = home / '.claude/settings.json'
claude_settings.parent.mkdir(exist_ok=True)
claude_settings.write_text('{"model":"keep-me","permissions":{"allow":["Read"]}}\n')
os.chown(claude_settings.parent, owner.pw_uid, owner.pw_gid)
os.chown(claude_settings, owner.pw_uid, owner.pw_gid)
project_claude_settings = project / '.claude/settings.local.json'
project_claude_settings.parent.mkdir(exist_ok=True)
project_claude_settings.write_text('{"permissions":{"deny":["Bash(rm *)"]}}\n')
os.chown(project_claude_settings.parent, owner.pw_uid, owner.pw_gid)
os.chown(project_claude_settings, owner.pw_uid, owner.pw_gid)
# This image supplies Pi and the Codex/Claude registration tooling. New native
# harness installers are exercised in their separate isolated host fixtures.
base = [command, 'setup', '--user', account, '--agent', 'codex', '--agent', 'claude-code',
        '--agent', 'pi', '--session', 'direct', '--yes']
for scope in ('user', 'project'):
    args = base + (['--scope', 'project', '--project', str(project)] if scope == 'project' else [])
    subprocess.run(args, check=True)
    configs = {p: p.read_bytes() for p in home.rglob('*') if p.is_file() and p.suffix in ('.json', '.toml') and 'lock' not in p.name}
    subprocess.run(args, check=True)
    for path, before in configs.items():
        after = path.read_bytes()
        if path.name == 'config.toml' and path.parent.name == '.codex':
            # Native hook installation first writes inline arrays. On repeat,
            # the original add-mcp formatter expands them to table arrays.
            # Preserve both upstream writers; every value, including exact
            # hook trust hashes and unrelated settings, must remain identical.
            assert tomllib.loads(after.decode()) == tomllib.loads(before.decode()), path
        else:
            assert after == before, path
    # Original Codex formatting must then converge, not change on every setup.
    stable = {p: p.read_bytes() for p in configs if p.name == 'config.toml' and p.parent.name == '.codex'}
    codex_args = [command, 'setup', '--user', account, '--agent', 'codex', '--session', 'direct', '--yes']
    if scope == 'project':
        codex_args += ['--scope', 'project', '--project', str(project)]
    subprocess.run(codex_args, check=True)
    assert all(p.read_bytes() == before for p, before in stable.items()), 'Codex formatting did not converge'
assert 'keep-me' in codex.read_text() and 'my-model' in codex.read_text()
assert 'mcp_servers.lcu' in codex.read_text()
user_claude = json.loads(claude_settings.read_text())
project_claude = json.loads(project_claude_settings.read_text())
assert user_claude['model'] == 'keep-me'
assert user_claude['permissions']['allow'] == ['Read']
host_only = ['mcp__lcu__turn_ended', 'mcp__lcu__js_add_node_module_dir', 'mcp__lcu__set_turn_context']
assert user_claude['permissions']['deny'] == host_only
assert project_claude['permissions']['deny'] == ['Bash(rm *)', *host_only]

# Claude invokes the shipped relay, which launches the original direct LCU
# command unchanged. Project registration belongs to the project .mcp.json.
expected_claude_command = [str(prefix / 'current/adapters/claude.mjs'), command]
for config_path in (home / '.claude.json', project / '.mcp.json'):
    registered = json.loads(config_path.read_text())['mcpServers']['lcu']
    assert registered['command'] == str(prefix / 'current/agent-tools/node/bin/node'), (config_path, registered)
    assert registered['args'] == expected_claude_command, (config_path, registered)

context_group = next(group for group in user_claude['hooks']['PreToolUse']
                     if group.get('matcher') == 'mcp__lcu__js|mcp__lcu__js_reset')
context_hook = context_group['hooks'][0]
assert (context_hook['type'], context_hook['server'], context_hook['tool']) == (
    'mcp_tool', 'lcu', 'set_turn_context')
assert context_hook['input'] == {
    'session_id': '${session_id}', 'turn_id': '${prompt_id}',
    'tool_use_id': '${tool_use_id}', 'agent_id': '${agent_id}',
}
for event, hook_event in (('Stop', 'Stop'), ('StopFailure', 'Interrupt')):
    cleanup = user_claude['hooks'][event][0]['hooks'][0]
    assert (cleanup['type'], cleanup['server'], cleanup['tool']) == ('mcp_tool', 'lcu', 'turn_ended')
    assert cleanup['input'] == {
        'hook_event_name': hook_event,
        'session_id': '${session_id}', 'turn_id': '${prompt_id}',
    }
pi_settings = home / '.pi/agent/settings.json'
assert pi_settings.is_file(), 'Pi local extension must be registered by its own package manager'
pi_packages = json.loads(pi_settings.read_text())['packages']
user_extension = home / '.local/share/lcu/pi/extension.mjs'
assert any((pi_settings.parent / item).resolve() == user_extension.resolve()
           for item in pi_packages if isinstance(item, str)), pi_packages
pi_commands = json.loads((home / '.local/share/lcu/pi/commands.json').read_text())
assert pi_commands['user'] == [command]
assert pi_commands['projects'][str(project.resolve())] == [command]
assert not (project / '.pi/lcu-command.json').exists()
project_pi_settings = project / '.pi/settings.json'
assert project_pi_settings.is_file(), 'Pi project extension must be registered independently'
project_pi_packages = json.loads(project_pi_settings.read_text())['packages']
assert any((project_pi_settings.parent / item).resolve() == user_extension.resolve()
           for item in project_pi_packages if isinstance(item, str)), project_pi_packages
browser_hosts = list((home / '.local/share/lcu/browser').glob('*/chrome/scripts/installManifest.mjs'))
assert not browser_hosts, 'Default desktop setup must not install a Chrome native host'
assert not (home / '.config/google-chrome/NativeMessagingHosts/com.openai.codexextension.json').exists()
resources = prefix / 'current/app/resources'
policy = json.loads((resources / 'plugins/openai-bundled/plugins/unified-computer-use/.mcp.json').read_text())['mcpServers']['cua_repl']
for path in (codex, project / '.codex/config.toml'):
    registered = tomllib.loads(path.read_text())['mcp_servers']['lcu']
    for key in ('enabled_tools', 'omit_tools_from', 'startup_timeout_sec', 'tools'):
        assert registered[key] == policy[key], (path, key)
for path in home.rglob('*'):
    assert path.lstat().st_uid == owner.pw_uid, path
export = home / 'portable'
if export.exists():
    import shutil
    shutil.rmtree(export)  # Disposable fixture owned by this test account.
subprocess.run([command, 'setup', '--user', account, '--export', str(export), '--session', 'direct', '--yes'], check=True)
config = json.loads((export / 'mcp.json').read_text())
assert config['mcpServers']['lcu']['command'] == '/bin/sh'
assert 'LCU_PREFIX' in config['mcpServers']['lcu']['args'][1]
assert '--chrome' not in config['mcpServers']['lcu']['args']
assert command not in config['mcpServers']['lcu']['args'][1]
assert not (home / '.local/share/lcu/skills/lcu/references/upstream/browser-desktop').exists()
assert not (home / '.local/share/lcu/skills/lcu/references/upstream/chrome').exists()
contract = json.loads((export / 'host-contract.json').read_text())
for key in ('enabled_tools', 'omit_tools_from', 'startup_timeout_sec', 'tools'):
    assert contract[key] == policy[key]
assert (export / 'skills/lcu/SKILL.md').is_file()
# Generated agent skill exposes original Linux references before a tool call.
registered_skills = [p.parent for p in home.rglob('SKILL.md')
                     if p.parent.name == 'lcu' and export not in p.parents]
assert registered_skills
module_root = resources / 'cua_node/lib/node_modules'
reference_pairs = (
    (module_root / '@oai/cua/docs/tinysky-alt-core-cua-repl.md', 'references/upstream/cua/docs/tinysky-alt-core-cua-repl.md'),
    (module_root / '@oai/cua-repl/instructions/linux/description.md', 'references/upstream/cua-repl/instructions/linux/description.md'),
    (module_root / '@oai/sky/docs/skills/oai_sky_lib/linux/SKILL.md', 'references/upstream/sky/linux/SKILL.md'),
    (module_root / '@oai/sky/docs/sky-full-desktop-api.md', 'references/upstream/sky/native-api.md'),
)
for skill in registered_skills:
    for original, relative in reference_pairs:
        assert (skill / relative).read_bytes() == original.read_bytes(), (skill, relative)
    assert not (skill / 'references/upstream/cua-repl/instructions/macos').exists(), skill
    assert not (skill / 'references/upstream/browser-desktop').exists(), skill
    assert not (skill / 'references/upstream/chrome').exists(), skill
# Portable exports carry bootstrap metadata, never upstream instruction files.
assert (export / 'lcu-bootstrap.json').is_file()
assert not (export / 'skills/lcu/references').exists()
upstream_sample = (module_root / '@oai/cua/docs/tinysky-alt-core-cua-repl.md').read_bytes()
assert upstream_sample not in b'\n'.join(p.read_bytes() for p in export.rglob('*') if p.is_file())
subprocess.run(['runuser', '-u', account, '--', 'python3',
                '/src/tests/portable_consumer.py', str(export)], check=True)
# Explicit browser setup installs the original connector and unified browser guide.
subprocess.run([command, 'setup', '--user', account, '--agent', 'codex', '--session', 'direct',
                '--chrome', '--yes'], check=True)
browser_hosts = list((home / '.local/share/lcu/browser').glob('*/chrome/scripts/installManifest.mjs'))
assert len(browser_hosts) == 1, 'Chrome opt-in must install one original native host'
assert (home / '.config/google-chrome/NativeMessagingHosts/com.openai.codexextension.json').is_file()
browser_guide = home / '.local/share/lcu/skills/lcu/references/upstream/browser-desktop/codex-app/api.json'
assert browser_guide.read_bytes() == (module_root / '@oai/browser-desktop/environment-docs/codex-app/api.json').read_bytes()
chrome_refs = home / '.local/share/lcu/skills/lcu/references/upstream/chrome'
original_chrome = resources / 'plugins/openai-bundled/plugins/chrome'
assert (chrome_refs / 'docs/documents.json').read_bytes() == (original_chrome / 'docs/documents.json').read_bytes()
assert (chrome_refs / 'skill/SKILL.md').read_bytes() == (original_chrome / 'skills/control-chrome/SKILL.md').read_bytes()
assert '--chrome' in tomllib.loads(codex.read_text())['mcp_servers']['lcu']['args']
browser_export = home / 'portable-chrome'
subprocess.run([command, 'setup', '--user', account, '--export', str(browser_export),
                '--session', 'direct', '--chrome', '--yes'], check=True)
assert json.loads((browser_export / 'mcp.json').read_text())['mcpServers']['lcu']['args'][-1] == '--chrome'
# A malformed existing supported-agent config must be left byte-for-byte intact.
claude = home / '.claude.json'
before = claude.read_bytes()
try:
    claude.write_bytes(b'{ not valid JSONC')
    failed = subprocess.run([command, 'setup', '--user', account, '--agent', 'claude-code', '--yes'], capture_output=True)
    assert failed.returncode != 0
    assert claude.read_bytes() == b'{ not valid JSONC'
finally:
    claude.write_bytes(before)
print('PASS: default desktop-only setup, explicit Chrome connector, Codex/Claude Code/Pi, scopes, ownership, idempotency, portable exports')
