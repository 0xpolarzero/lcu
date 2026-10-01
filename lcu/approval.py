"""Optional approval mode: add or remove only LCU's own harness approval entries.

`auto` lets each selected harness run LCU's computer-use tools without its own
per-call prompt. LCU records what `auto` changed (per config path, profile and
scope, with any prior Codex value) in `approval.json` beside `setup.json`, and
`ask` reverses exactly that. An entry LCU did not add, even one identical to
what `auto` writes, is never removed; it is left alone and reported.

Native-app and Chrome approvals come from the original runtime and are not
affected. Chrome site approvals stay exact-origin only.
"""
import json
import shutil
import subprocess
from pathlib import Path

MODES = ('ask', 'auto')

# Claude Code: a permission rule for every tool of the `lcu` MCP server. The
# host-only tools stay denied because deny rules take precedence over allow.
CLAUDE_RULE = 'mcp__lcu'
# Codex: a server-level default for the `lcu` MCP server's own table.
CODEX_KEY = 'default_tools_approval_mode'
CODEX_VALUE = 'approve'
# OMP: per-tool policies for the two tools the LCU extension registers.
OMP_TOOLS = ('js', 'js_reset')

NOTHING_TO_CONFIGURE = {
    'pi': 'Pi has no permission system; nothing to configure',
    'hermes': 'Hermes gates only plugin tools through a pre_tool_call hook, which LCU does not register; '
              'nothing to configure',
}


def record_path(home):
    """LCU's own record of what approval mode changed, beside setup.json."""
    from .setup import setup_state_path
    return setup_state_path(Path(home)).with_name('approval.json')


def load_record(home):
    from .setup import read_file
    path = record_path(home)
    data = read_file(path)
    if data is None:
        return {}
    try:
        record = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        record = None
    if not isinstance(record, dict) or not all(isinstance(value, dict) for value in record.values()):
        raise ValueError(f'Malformed LCU approval record at {path}; check it, then delete it and rerun setup.')
    return record


def save_record(home, record):
    from .setup import atomic_write
    atomic_write(record_path(home), (json.dumps(record, indent=2, sort_keys=True) + '\n').encode())


def _commit(home, key, value):
    """Store (or, with None, forget) what LCU changed for one config location."""
    record = load_record(home)
    if value is None:
        if key not in record:
            return
        del record[key]
    else:
        record[key] = value
    save_record(home, record)


KEEP = 'keep'  # codex_plan: leave the stored record as it is


def codex_config_path(home, scope, project, env):
    from .codex_hooks import _selected_codex_home
    if scope == 'project':
        return Path(project) / '.codex/config.toml'
    return _selected_codex_home({**env, 'HOME': env.get('HOME', str(home))}) / 'config.toml'


def _codex_value(path):
    from .setup import read_file
    import tomllib
    data = read_file(path)
    if data is None:
        return None
    servers = tomllib.loads(data.decode()).get('mcp_servers')
    table = servers.get('lcu') if isinstance(servers, dict) else None
    value = table.get(CODEX_KEY) if isinstance(table, dict) else None
    return value if isinstance(value, str) else None


def codex_plan(mode, home, *, scope, project, env):
    """Decide the `default_tools_approval_mode` registration writes for `[mcp_servers.lcu]`.

    Registration replaces that whole table (it is LCU's own), so a value the user set
    there must be carried through explicitly: `auto` records it as the prior value,
    `ask` restores it, and anything LCU did not record is preserved as the user's.
    Returns {'policy': keys merged at registration, 'key': record key, 'record': what to
    store once registration succeeds (None forgets it, KEEP leaves it)}.
    """
    path = codex_config_path(home, scope, project, env)
    key = f'codex|{path}'
    try:
        current = _codex_value(path)
        record = load_record(home)
    except (ValueError, UnicodeDecodeError) as exc:
        if mode is None:
            return {'policy': {}, 'key': key, 'record': KEEP}
        raise ValueError(f'Cannot read the Codex config at {path}: {exc}') from exc
    recorded = record.get(key)
    if mode == 'auto':
        if recorded is not None and current in (CODEX_VALUE, None):
            prior = recorded.get('prior')
        else:
            prior = current
        return {'policy': {CODEX_KEY: CODEX_VALUE}, 'key': key, 'record': {'prior': prior}}
    if recorded is not None and mode == 'ask':
        prior = recorded.get('prior')
        return {'policy': {CODEX_KEY: prior} if isinstance(prior, str) else {}, 'key': key, 'record': None,
                'restored': prior}
    # Not recorded (or no explicit mode): whatever is there belongs to the user.
    return {'policy': {CODEX_KEY: current} if current is not None else {}, 'key': key, 'record': KEEP}


def claude_settings_path(home, project=None):
    return (Path(project) / '.claude/settings.local.json') if project else (Path(home) / '.claude/settings.json')


def apply_claude(mode, home, *, project=None):
    from .setup import Change, apply_changes, read_file
    path = claude_settings_path(home, project)
    key = f'claude-code|{path}'
    recorded = key in load_record(home)
    before = read_file(path)
    if before is None and mode != 'auto':
        _commit(home, key, None)
        return 'unchanged (no settings file)'
    settings = json.loads(before) if before else {}
    if not isinstance(settings, dict):
        raise ValueError(f'Claude settings must be an object: {path}')
    permissions = settings.setdefault('permissions', {})
    if not isinstance(permissions, dict):
        raise ValueError(f'Claude permissions must be an object: {path}')
    allow = permissions.get('allow', [])
    if not isinstance(allow, list) or any(not isinstance(rule, str) for rule in allow):
        raise ValueError(f'Claude allow rules must be a string array: {path}')
    note = ''
    if mode == 'auto':
        outcome = 'unchanged' if CLAUDE_RULE in allow else 'added'
        if outcome == 'added':
            permissions['allow'] = [*allow, CLAUDE_RULE]
    else:
        # Only an entry LCU recorded adding is LCU's to remove.
        outcome = 'removed' if recorded and CLAUDE_RULE in allow else 'unchanged'
        if outcome == 'removed':
            remaining = [rule for rule in allow if rule != CLAUDE_RULE]
            if remaining:
                permissions['allow'] = remaining
            else:
                del permissions['allow']
            if not permissions:
                del settings['permissions']
        elif CLAUDE_RULE in allow:
            note = f'; kept your own `{CLAUDE_RULE}` rule, which LCU did not add'
    if outcome != 'unchanged':
        apply_changes([Change(path, before, (json.dumps(settings, indent=2) + '\n').encode())])
    if mode == 'auto':
        if outcome == 'added':
            _commit(home, key, {'added': [CLAUDE_RULE]})
    else:
        _commit(home, key, None)
    return f'{outcome} `{CLAUDE_RULE}` in permissions.allow ({path}){note}'


def _omp(executable, env, home, *args):
    result = subprocess.run([executable, 'config', *args], cwd=home, env=env, stdin=subprocess.DEVNULL,
                            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise ValueError(f'omp config exited {result.returncode}' + (f': {detail}' if detail else ''))
    return result.stdout


def _omp_key(home, env):
    profile = {name: env[name] for name in ('PI_CODING_AGENT_DIR', 'OMP_PROFILE') if env.get(name)}
    return f'omp|{home}|{json.dumps(profile, sort_keys=True)}'


def apply_omp(mode, home, *, env):
    executable = shutil.which('omp', path=env.get('PATH'))
    if not executable:
        raise ValueError('Oh My Pi is not on the target account PATH. Install OMP, then rerun setup.')
    key = _omp_key(home, env)
    added = set(load_record(home).get(key, {}).get('added', []))
    try:
        current = json.loads(_omp(executable, env, home, 'get', 'tools.approval', '--json'))['value']
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError('omp config returned an unexpected tools.approval value') from exc
    if not isinstance(current, dict):
        raise ValueError('OMP tools.approval must be a mapping of tool names to policies')
    updated, notes = dict(current), []
    for tool in OMP_TOOLS:
        if mode == 'auto':
            if tool not in updated:
                updated[tool] = 'allow'
                added.add(tool)
                notes.append(f'added `{tool}: allow`')
            elif updated[tool] != 'allow':
                added.discard(tool)
                notes.append(f'kept your `{tool}: {updated[tool]}`')
        elif tool in added and updated.get(tool) == 'allow':
            del updated[tool]
            notes.append(f'removed `{tool}: allow`')
        elif tool in updated:
            notes.append(f'kept your `{tool}: {updated[tool]}`, which LCU did not add')
    if updated != current:
        if updated:
            _omp(executable, env, home, 'set', 'tools.approval', json.dumps(updated, sort_keys=True))
        else:
            _omp(executable, env, home, 'reset', 'tools.approval')
    _commit(home, key, {'added': sorted(added)} if mode == 'auto' and added else None)
    return ', '.join(notes) + ' in tools.approval' if notes else 'unchanged'


def apply(mode, name, home, *, scope, project, env, plan=None):
    """Apply an approval mode for one harness; return a short description.

    `plan` is the `codex_plan` computed before registration, which is when the
    previous Codex value is still readable.
    """
    if mode not in MODES:
        raise ValueError(f'Unknown approval mode: {mode}')
    if name == 'claude-code':
        return apply_claude(mode, home, project=project if scope == 'project' else None)
    if name == 'omp':
        return apply_omp(mode, home, env=env)
    if name == 'codex':
        if plan is None:
            plan = codex_plan(mode, home, scope=scope, project=project, env=env)
        if plan['record'] != KEEP:
            _commit(home, plan['key'], plan['record'])
        if mode == 'auto':
            return 'registered `default_tools_approval_mode = "approve"` for `[mcp_servers.lcu]`'
        restored = plan.get('restored')
        return (f'restored your previous `default_tools_approval_mode = "{restored}"` for `[mcp_servers.lcu]`'
                if isinstance(restored, str)
                else 'registered `[mcp_servers.lcu]` without a `default_tools_approval_mode` LCU added')
    return NOTHING_TO_CONFIGURE[name]
