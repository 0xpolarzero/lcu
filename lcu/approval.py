"""Optional approval mode: add or remove only LCU's own harness approval entries.

`auto` lets each selected harness run LCU's computer-use tools without its own
per-call prompt. `ask` removes exactly the entries `auto` added and leaves the
harness defaults in force. Nothing else is touched, and an entry the user set
to something other than what `auto` writes is left alone and reported.

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


def codex_policy(mode):
    """Keys merged into the Codex `[mcp_servers.lcu]` table at registration.

    Registration replaces that whole table (it is LCU's own), so omitting the key
    is what removes it.
    """
    return {CODEX_KEY: CODEX_VALUE} if mode == 'auto' else {}


def claude_settings_path(home, project=None):
    return (Path(project) / '.claude/settings.local.json') if project else (Path(home) / '.claude/settings.json')


def apply_claude(mode, home, *, project=None):
    from .setup import Change, apply_changes, read_file
    path = claude_settings_path(home, project)
    before = read_file(path)
    if before is None and mode != 'auto':
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
    if mode == 'auto':
        outcome = 'unchanged' if CLAUDE_RULE in allow else 'added'
        if outcome == 'added':
            permissions['allow'] = [*allow, CLAUDE_RULE]
    else:
        outcome = 'removed' if CLAUDE_RULE in allow else 'unchanged'
        if outcome == 'removed':
            remaining = [rule for rule in allow if rule != CLAUDE_RULE]
            if remaining:
                permissions['allow'] = remaining
            else:
                del permissions['allow']
            if not permissions:
                del settings['permissions']
    if outcome != 'unchanged':
        apply_changes([Change(path, before, (json.dumps(settings, indent=2) + '\n').encode())])
    return f'{outcome} `{CLAUDE_RULE}` in permissions.allow ({path})'


def _omp(executable, env, home, *args):
    result = subprocess.run([executable, 'config', *args], cwd=home, env=env, stdin=subprocess.DEVNULL,
                            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise ValueError(f'omp config exited {result.returncode}' + (f': {detail}' if detail else ''))
    return result.stdout


def apply_omp(mode, home, *, env):
    executable = shutil.which('omp', path=env.get('PATH'))
    if not executable:
        raise ValueError('Oh My Pi is not on the target account PATH. Install OMP, then rerun setup.')
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
                notes.append(f'added `{tool}: allow`')
            elif updated[tool] != 'allow':
                notes.append(f'kept your `{tool}: {updated[tool]}`')
        elif updated.get(tool) == 'allow':
            del updated[tool]
            notes.append(f'removed `{tool}: allow`')
    if updated != current:
        if updated:
            _omp(executable, env, home, 'set', 'tools.approval', json.dumps(updated, sort_keys=True))
        else:
            _omp(executable, env, home, 'reset', 'tools.approval')
    return ', '.join(notes) + ' in tools.approval' if notes else 'unchanged'


def apply(mode, name, home, *, scope, project, env):
    """Apply an approval mode for one harness; return a short description."""
    if mode not in MODES:
        raise ValueError(f'Unknown approval mode: {mode}')
    if name == 'claude-code':
        return apply_claude(mode, home, project=project if scope == 'project' else None)
    if name == 'omp':
        return apply_omp(mode, home, env=env)
    if name == 'codex':
        return ('registered `default_tools_approval_mode = "approve"` for `[mcp_servers.lcu]`' if mode == 'auto'
                else 'registered `[mcp_servers.lcu]` without `default_tools_approval_mode`')
    return NOTHING_TO_CONFIGURE[name]
