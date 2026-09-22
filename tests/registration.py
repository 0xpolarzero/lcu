"""Run as root in the disposable container; inspect another account's outputs."""
import json
import os
from pathlib import Path
import pwd
import subprocess

prefix = Path('/opt/cual')
command = str(prefix / 'current/bin/cual')
account = 'cualtester'
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
    assert all(p.read_bytes() == before for p, before in configs.items()), 'Registration is not idempotent'
assert 'keep-me' in codex.read_text() and 'my-model' in codex.read_text()
assert 'mcp_servers.cual' in codex.read_text()
for path in home.rglob('*'):
    assert path.lstat().st_uid == owner.pw_uid, path
export = home / 'portable'
if export.exists():
    import shutil
    shutil.rmtree(export)  # Disposable fixture owned by this test account.
subprocess.run([command, 'setup', '--user', account, '--export', str(export), '--session', 'direct', '--yes'], check=True)
config = json.loads((export / 'mcp.json').read_text())
assert config['mcpServers']['cual']['command'] == command
assert (export / 'skills/cual/SKILL.md').is_file()
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
