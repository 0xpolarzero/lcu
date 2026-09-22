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
policy = json.loads((prefix / 'current/host/plugins/unified-computer-use/.mcp.json').read_text())['mcpServers']['cua_repl']
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
assert config['mcpServers']['lcu']['command'] == command
contract = json.loads((export / 'host-contract.json').read_text())
for key in ('enabled_tools', 'omit_tools_from', 'startup_timeout_sec', 'tools'):
    assert contract[key] == policy[key]
assert (export / 'skills/lcu/SKILL.md').is_file()
# Complete references must survive every upstream installer and portable export.
registered_skills = [p.parent for p in home.rglob('SKILL.md') if p.parent.name == 'lcu']
assert registered_skills
for skill in registered_skills:
    for name in ('api.md', 'linux-desktop.md'):
        assert (skill / 'references' / name).read_bytes() == (prefix / 'current/skills/lcu/references' / name).read_bytes(), skill
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
print('PASS: seven agents, user and project scope, account ownership, config preservation, idempotency, portable export')
