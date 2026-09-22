"""Configure LCU tools and skill together, without requiring a running desktop."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import json
import os
from pathlib import Path
import pwd
import shutil
import shlex
import subprocess
import sys
import tempfile

from .setup_clients import CLIENTS, ALIASES


@dataclass
class Change:
    path: Path
    before: bytes | None
    after: bytes | None


def regular_path(path):
    """Do not write through symlinks, including directory components."""
    path = Path(path).absolute()
    if '..' in path.parts or any(ord(c) < 32 for c in str(path)):
        raise ValueError(f'Use a path without parent traversal or control characters: {path}')
    for item in (path, *path.parents):
        if item.is_symlink():
            raise ValueError(f'Refusing a symlink in setup destination: {item}. Use manual configuration instead.')
    return path


def read_file(path):
    regular_path(path)
    if path.exists():
        if not path.is_file():
            raise ValueError(f'Expected a regular file: {path}')
        return path.read_bytes()
    return None


def tree_files(path):
    regular_path(path)
    if not path.exists():
        return {}
    if not path.is_dir():
        raise ValueError(f'Expected a skill directory: {path}')
    result = {}
    for item in path.rglob('*'):
        regular_path(item)
        if item.is_file():
            result[str(item.relative_to(path))] = item.read_bytes()
        elif not item.is_dir():
            raise ValueError(f'Unsupported skill file: {item}')
    return result


def atomic_write(path, data):
    regular_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if data is None:
        path.unlink(missing_ok=True)
        return
    previous_mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    fd, temporary = tempfile.mkstemp(prefix='.lcu-setup-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, previous_mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def apply_changes(changes):
    """Preflight everything; roll back our writes if a later write fails."""
    changes = [c for c in changes if c.before != c.after]
    for change in changes:
        if read_file(change.path) != change.before:
            raise ValueError(f'File changed during setup; retry: {change.path}')
    applied = []
    try:
        for change in changes:
            if read_file(change.path) != change.before:
                raise ValueError(f'File changed during setup; retry: {change.path}')
            atomic_write(change.path, change.after)
            applied.append(change)
    except BaseException:
        for change in reversed(applied):
            # Never undo a concurrent editor's changes.
            if read_file(change.path) == change.after:
                atomic_write(change.path, change.before)
        raise
    return len(changes)


@contextmanager
def setup_lock(home):
    path = regular_path(home / '.local/state/lcu/setup.lock')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def installer_environment(home, names, environ=None):
    """Select a real account home; only honor profile overrides understood upstream."""
    env = dict(os.environ if environ is None else environ)
    rejected = {
        'claude-code': ('CLAUDE_CONFIG_DIR',),
        'gemini-cli': ('GEMINI_CLI_HOME',),
        'opencode': ('OPENCODE_CONFIG', 'OPENCODE_CONFIG_DIR'),
        'copilot-cli': ('COPILOT_HOME',),
    }
    for name in names:
        for variable in rejected.get(name, ()):
            if env.get(variable):
                raise ValueError(f'{variable} is not supported by the bundled installers for {name}; unset it or use --export.')
    supported = []
    if 'codex' in names:
        supported.append('CODEX_HOME')
    if {'opencode', 'vscode', 'copilot-cli'} & set(names):
        supported.append('XDG_CONFIG_HOME')
    for variable in supported:
        if env.get(variable) and not Path(env[variable]).is_absolute():
            raise ValueError(f'{variable} must be absolute.')
    if 'copilot-cli' in names and env.get('XDG_CONFIG_HOME'):
        raise ValueError('XDG_CONFIG_HOME is not supported for Copilot CLI by the bundled installers; unset it or use --export.')
    env.update(HOME=str(home), DISABLE_TELEMETRY='1', DO_NOT_TRACK='1', NO_COLOR='1', CI='1')
    # Node flags can inject code; setup uses only the packaged runtime and CLIs.
    env.pop('NODE_OPTIONS', None)
    env.pop('NODE_PATH', None)
    return env


def installer_paths(tools_root):
    paths = (tools_root / 'node/bin/node',
             tools_root / 'node_modules/skills/bin/cli.mjs',
             tools_root / 'node_modules/add-mcp/dist/index.js')
    for path in paths:
        if not path.is_file():
            raise ValueError(f'Bundled agent installer missing: {path}. Rerun scripts/install.sh with this --prefix.')
    if not os.access(paths[0], os.X_OK):
        raise ValueError(f'Bundled Node runtime is not executable: {paths[0]}')
    return paths


# add-mcp 2.4.0 accepts malformed JSONC without checking parse errors. Keep this
# read-only guard until upstream fails closed. Paths and formats still come from
# its public adapter metadata; all configuration writes remain upstream-owned.
MCP_PREFLIGHT = r"""
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
try {
  const [cli, name, scope] = process.argv.slice(1);
  const require = createRequire(pathToFileURL(cli));
  const { agents } = await import(pathToFileURL(join(dirname(cli), 'lib.js')));
  const agent = agents[name];
  const local = scope === 'project';
  const cwd = process.cwd();
  const path = agent.resolveConfigPath ? agent.resolveConfigPath(agent, { local, cwd })
    : local ? join(cwd, agent.localConfigPath) : agent.configPath;
  let text;
  try { text = readFileSync(path, 'utf8'); }
  catch (error) { if (error.code === 'ENOENT') process.exit(0); throw error; }
  let data;
  if (agent.format === 'toml') data = require('@iarna/toml').parse(text);
  else if (agent.format === 'json') {
    const jsonc = require('jsonc-parser');
    const errors = [];
    const tree = jsonc.parseTree(text, errors, { allowTrailingComma: true });
    if (errors.length) throw new Error(`Malformed configuration: ${path}`);
    function checkDuplicates(node) {
      if (!node) return;
      if (node.type === 'object') {
        const keys = new Set();
        for (const property of node.children || []) {
          const key = property.children[0].value;
          if (keys.has(key)) throw new Error(`Duplicate configuration key in ${path}: ${key}`);
          keys.add(key);
        }
      }
      for (const child of node.children || []) checkDuplicates(child);
    }
    checkDuplicates(tree);
    data = jsonc.getNodeValue(tree);
  } else throw new Error(`Unsupported configuration format: ${agent.format}`);
  const object = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
  if (!object(data)) throw new Error(`Configuration must be an object: ${path}`);
  const key = local && agent.localConfigKey ? agent.localConfigKey : agent.configKey;
  let current = data;
  for (const part of key.split('.')) {
    if (!Object.hasOwn(current, part)) break;
    current = current[part];
    if (!object(current)) throw new Error(`MCP configuration must be an object: ${path}`);
  }
} catch (error) { console.error(error.message); process.exitCode = 1; }
"""


def preflight_mcp(node, mcp, client, scope, cwd, env):
    result = subprocess.run([str(node), '--input-type=module', '-e', MCP_PREFLIGHT,
                             str(mcp), client.mcp_agent, scope], cwd=cwd, env=env,
                            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise ValueError(result.stderr.strip() or 'MCP configuration preflight failed')


def configure(names, home, source, command, tools_root, *, scope='user', project=None, environ=None):
    """Delegate registration and return phase failures; no client executable needed."""
    env = installer_environment(home, names, environ)
    node, skills, mcp = installer_paths(tools_root)
    if not (source / 'SKILL.md').is_file():
        raise ValueError(f'Complete LCU skill missing: {source}')
    cwd = project if scope == 'project' else home
    global_args = ['--global'] if scope == 'user' else []
    failures = []
    for name in names:
        client = CLIENTS[name]
        commands = (
            ('skill', [str(node), str(skills), 'add', str(source), '--skill', 'lcu',
                       '--agent', client.skills_agent, '--copy', '--yes', '--json', *global_args]),
            ('MCP', [str(node), str(mcp), command[0], '--name', 'lcu',
                     '--agent', client.mcp_agent, '--yes', *global_args,
                     *['--args=' + arg for arg in command[1:]]]),
        )
        for phase, argv in commands:
            try:
                if phase == 'MCP':
                    preflight_mcp(node, mcp, client, scope, cwd, env)
                result = subprocess.run(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                        capture_output=True, text=True, timeout=120)
                if result.returncode:
                    # Upstream diagnostics are shown to the invoking user, never stored.
                    detail = (result.stderr or result.stdout).strip()
                    raise ValueError(f'installer exited {result.returncode}' + (f': {detail}' if detail else ''))
                if phase == 'skill':
                    try:
                        installed = json.loads(result.stdout)
                    except json.JSONDecodeError as exc:
                        raise ValueError('skill installer returned invalid JSON') from exc
                    if not isinstance(installed, list) or not any(
                        isinstance(item, dict) and item.get('name') == 'lcu'
                        and item.get('status') == 'installed' for item in installed
                    ):
                        raise ValueError('skill installer did not report installing LCU')
                print(f'{client.label}: {phase} registered.')
            except (ValueError, OSError, subprocess.SubprocessError) as exc:
                failures.append((name, phase, str(exc)))
                print(f'{client.label}: {phase} failed: {exc}', file=sys.stderr)
    return failures


def export_bundle(destination, source, command):
    destination = regular_path(destination)
    if destination.exists():
        raise ValueError('Export destination already exists; choose a new directory.')
    files = tree_files(source)
    if 'SKILL.md' not in files:
        raise ValueError('Complete LCU skill missing.')
    manifest = {'$schema': 'https://agent-plugins.org/schemas/1.0.0/plugin.schema.json',
                'name': 'lcu', 'description': 'Computer use for AI agents on Linux.'}
    mcp = {'mcpServers': {'lcu': {'type': 'stdio', 'command': command[0], 'args': command[1:]}}}
    changes = [Change(destination / 'plugin.json', None, (json.dumps(manifest, indent=2) + '\n').encode()),
               Change(destination / 'mcp.json', None, (json.dumps(mcp, indent=2) + '\n').encode())]
    changes += [Change(destination / 'skills/lcu' / name, None, data) for name, data in files.items()]
    apply_changes(changes)


def parser():
    p = argparse.ArgumentParser(description=__doc__, epilog='Run on the machine hosting the agent backend. For Codex SSH remote projects, that is the VM. This command never installs or authenticates the agent itself.')
    p.add_argument('--prefix', type=Path, default=Path('/opt/lcu'), help='Managed runtime prefix (default: /opt/lcu)')
    p.add_argument('--user', help='Target Linux account; root must select one explicitly')
    p.add_argument('--agent', action='append', default=[], help='Agent ID; repeat for several, all for every supported client, or auto for detected clients. Use --list-agents.')
    p.add_argument('--scope', choices=['user', 'project'], default='user')
    p.add_argument('--project', type=Path, help='Absolute existing project directory for project scope')
    p.add_argument('--yes', action='store_true', help='Apply explicit choices without a confirmation prompt')
    p.add_argument('--list-agents', action='store_true', help='List supported adapters and exit')
    p.add_argument('--export', type=Path, help='Export a portable tools-and-skill plugin for custom clients to a new directory')
    p.add_argument('--session', choices=['discover', 'direct'], default='discover', help='discover attaches through lcu-session (XFCE); direct inherits agent desktop environment')
    p.add_argument('--check-desktop', action='store_true', help='Also require a live desktop readiness check; omit while building images')
    p.add_argument('--validate-only', action='store_true', help=argparse.SUPPRESS)
    return p


def validate(args):
    prefix = args.prefix
    if not prefix.is_absolute() or len(prefix.parts) < 3 or '..' in prefix.parts or any(ord(c) < 32 for c in str(prefix)):
        raise ValueError('Use a dedicated absolute prefix, such as /opt/lcu.')
    if os.getuid() == 0 and args.user is None:
        raise ValueError('Root must specify --user ACCOUNT.')
    try:
        account = pwd.getpwnam(args.user) if args.user else pwd.getpwuid(os.getuid())
    except KeyError:
        raise ValueError('The selected Linux account does not exist. Create it before setup.') from None
    if os.getuid() not in (0, account.pw_uid):
        raise ValueError('Run as the selected account or root.')
    if not Path(account.pw_dir).is_absolute() or not Path(account.pw_dir).is_dir():
        raise ValueError('Selected account must have an existing absolute home directory.')
    if args.scope == 'project':
        if not args.project or not args.project.is_absolute() or not args.project.is_dir():
            raise ValueError('--scope project requires --project with an existing absolute directory.')
    elif args.project:
        raise ValueError('--project requires --scope project.')
    if args.export and args.agent:
        raise ValueError('Choose --export or --agent, not both.')
    if args.export:
        if not args.export.is_absolute():
            raise ValueError('--export requires an absolute path.')
        regular_path(args.export)
        if args.export.exists():
            raise ValueError('Export destination already exists; choose a new directory.')
    names = list(dict.fromkeys(ALIASES.get(name, name) for name in args.agent))
    unknown = set(names) - set(CLIENTS) - {'auto', 'all'}
    if unknown:
        raise ValueError('Unknown agent: ' + ', '.join(sorted(unknown)) + '. Run lcu setup --list-agents, or use --export for a custom client.')
    if {'auto', 'all'} & set(names) and len(names) > 1:
        raise ValueError('Use --agent all or --agent auto alone, or select explicit agent IDs.')
    if names == ['all']:
        names = list(CLIENTS)
    return account, names


def detect(home):
    return [name for name, client in CLIENTS.items()
            if shutil.which(client.executable) or (home / client.detect_path).exists()]


def choose_agents(home):
    detected = detect(home)
    print('Select one or more agents for this account (comma-separated IDs).')
    for name, client in CLIENTS.items():
        print(f'  {name:16} {client.label}' + (' [detected]' if name in detected else ''))
    print('Use all for every supported client, including those not installed yet.\nFor other clients, cancel and use --export /absolute/new/plugin-directory.')
    answer = input('Agents: ').strip()
    names = list(dict.fromkeys(ALIASES.get(n.strip(), n.strip()) for n in answer.split(',') if n.strip()))
    if names == ['all']:
        return list(CLIENTS)
    if names == ['auto']:
        names = detected
    if not names or any(name not in CLIENTS for name in names):
        raise ValueError('Choose supported agent IDs, or use --export for a custom client.')
    return names


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    if args.list_agents:
        for name, client in CLIENTS.items():
            print(f'{name:16} {client.label} (user, project)')
        print('Custom clients: --export /absolute/new/plugin-directory')
        return
    try:
        account, names = validate(args)
        if args.validate_only:
            if not args.export:
                # Another account must never inherit the caller's profile overrides.
                environment = {} if os.getuid() == 0 and account.pw_uid != 0 else os.environ
                installer_environment(Path(account.pw_dir), names, environment)
            return
        # Account files are always written as their owner, including image builds.
        if os.getuid() == 0 and account.pw_uid != 0:
            os.initgroups(account.pw_name, account.pw_gid)
            os.setgid(account.pw_gid)
            os.setuid(account.pw_uid)
            os.environ.clear()
            os.environ.update(HOME=account.pw_dir, USER=account.pw_name, LOGNAME=account.pw_name,
                              PATH=f'{account.pw_dir}/.local/bin:/usr/local/bin:/usr/bin:/bin', LANG='C.UTF-8')
            os.chdir(account.pw_dir)
        home = Path(account.pw_dir)
        runtime = args.prefix / 'current/bin/lcu'
        launcher = args.prefix / 'current/bin/lcu-session'
        source = (args.prefix / 'current/skills/lcu').resolve()
        for path in (runtime, launcher):
            if not path.is_file() or not os.access(path, os.X_OK):
                raise ValueError(f'Managed runtime missing or inaccessible: {path}. Run scripts/install.sh first, or select its --prefix.')
        command = [str(runtime)] if args.session == 'direct' else [str(launcher), '--user', account.pw_name, '--', str(runtime)]
        if names == ['auto']:
            names = detect(home)
            if not names:
                raise ValueError('No agents detected. Select --agent explicitly (works before the agent is installed), or use --export.')
        if not names and not args.export:
            if not sys.stdin.isatty():
                raise ValueError('Noninteractive setup requires --agent ID (repeatable), --agent all, --agent auto, or --export PATH.')
            names = choose_agents(home)
        subprocess.run([str(runtime), '--version'], check=True, timeout=20, stdout=subprocess.DEVNULL)
        tools_root = args.prefix / 'current/agent-tools'
        if not args.export:
            installer_environment(home, names)
            installer_paths(tools_root)
        with setup_lock(home):
            if args.export:
                print(f'Export tools and skill to {args.export}')
            else:
                print(f'Configure {", ".join(names)} for {account.pw_name} ({args.scope} scope).')
                print('Existing LCU skill and MCP entries will be updated; unrelated configuration is preserved.')
            if not args.yes:
                if not sys.stdin.isatty():
                    raise ValueError('Review the selection above, then rerun with --yes for noninteractive setup.')
                if input('Apply this setup? [y/N] ').strip().lower() not in ('y', 'yes'):
                    print('Cancelled; no agent configuration changed.')
                    return
            if args.export:
                export_bundle(args.export, source, command)
            else:
                failures = configure(names, home, source, command, tools_root,
                                     scope=args.scope, project=args.project)
                if failures:
                    retry = [str(runtime), 'setup', '--prefix', str(args.prefix), '--user', account.pw_name,
                             '--scope', args.scope, '--session', args.session, '--yes']
                    if args.project:
                        retry += ['--project', str(args.project)]
                    for name in dict.fromkeys(item[0] for item in failures):
                        retry += ['--agent', name]
                    raise ValueError(f'{len(failures)} registration step(s) failed. Completed steps remain installed. '
                                     + 'After resolving the errors, retry: ' + shlex.join(retry))
        print('Configuration prepared. Restart/reconnect the selected agent, then ask it to use LCU to inspect the desktop.')
        if args.export:
            print('Import this plugin with a compatible client, or use its mcp.json and skills/lcu with your custom agent. Its command runs on this Linux machine.')
        if args.check_desktop:
            print('Checking the live desktop...')
            subprocess.run([*command, 'doctor'], check=True, timeout=35)
            print('Desktop readiness check passed. Tool and skill discovery inside the agent still needs its first connection.')
        else:
            print('Live desktop not checked (image builds need no running GUI). After starting the desktop, check with:')
            print('  ' + shlex.join([*command, 'doctor']))
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        p.exit(1, f'Setup failed: {exc}\n')


if __name__ == '__main__':
    main()
