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
base = [command, 'setup', '--user', account, '--agent', 'all', '--session', 'direct', '--yes']
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
browser_hosts = list((home / '.local/share/lcu/browser').glob('*/chrome/scripts/installManifest.mjs'))
assert len(browser_hosts) == 1, 'Setup must install one original native host for this account'
assert (home / '.config/google-chrome/NativeMessagingHosts/com.openai.codexextension.json').is_file()
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
assert command not in config['mcpServers']['lcu']['args'][1]
assert (home / '.local/share/lcu/skills/lcu/references/upstream/chrome/skill/SKILL.md').is_file()
contract = json.loads((export / 'host-contract.json').read_text())
for key in ('enabled_tools', 'omit_tools_from', 'startup_timeout_sec', 'tools'):
    assert contract[key] == policy[key]
assert (export / 'skills/lcu/SKILL.md').is_file()
# Generated agent skill exposes original Linux and Chrome references before a tool call.
registered_skills = [p.parent for p in home.rglob('SKILL.md')
                     if p.parent.name == 'lcu' and export not in p.parents]
assert registered_skills
module_root = resources / 'cua_node/lib/node_modules'
reference_pairs = (
    (module_root / '@oai/cua/docs/tinysky-alt-core-cua-repl.md', 'references/upstream/cua/docs/tinysky-alt-core-cua-repl.md'),
    (module_root / '@oai/cua-repl/instructions/linux/description.md', 'references/upstream/cua-repl/instructions/linux/description.md'),
    (module_root / '@oai/sky/docs/skills/oai_sky_lib/linux/SKILL.md', 'references/upstream/sky/linux/SKILL.md'),
    (module_root / '@oai/sky/docs/sky-full-desktop-api.md', 'references/upstream/sky/native-api.md'),
    (resources / 'plugins/openai-bundled/plugins/chrome/skills/control-chrome/SKILL.md', 'references/upstream/chrome/skill/SKILL.md'),
    (resources / 'plugins/openai-bundled/plugins/chrome/docs/documents.json', 'references/upstream/chrome/docs/documents.json'),
)
for skill in registered_skills:
    for original, relative in reference_pairs:
        assert (skill / relative).read_bytes() == original.read_bytes(), (skill, relative)
    assert not (skill / 'references/upstream/cua-repl/instructions/macos').exists(), skill
# Portable exports carry bootstrap metadata, never upstream instruction files.
assert (export / 'lcu-bootstrap.json').is_file()
assert not (export / 'skills/lcu/references').exists()
upstream_sample = (module_root / '@oai/cua/docs/tinysky-alt-core-cua-repl.md').read_bytes()
assert upstream_sample not in b'\n'.join(p.read_bytes() for p in export.rglob('*') if p.is_file())
subprocess.run(['runuser', '-u', account, '--', 'python3',
                '/src/tests/portable_consumer.py', str(export)], check=True)
# A malformed existing config must be left byte-for-byte intact.
cursor = home / '.cursor/mcp.json'
before = cursor.read_bytes()
try:
    cursor.write_bytes(b'{ not valid JSONC')
    failed = subprocess.run([command, 'setup', '--user', account, '--agent', 'cursor', '--yes'], capture_output=True)
    assert failed.returncode != 0
    assert cursor.read_bytes() == b'{ not valid JSONC'
finally:
    cursor.write_bytes(before)
print('PASS: seven agents, browser native host, user and project scope, account ownership, config preservation, idempotency, portable export')
