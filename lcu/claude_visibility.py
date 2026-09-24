"""Keep the original CUA host-only tools out of Claude Code's model context."""
import json
from pathlib import Path


HOST_ONLY = ('mcp__lcu__turn_ended', 'mcp__lcu__js_add_node_module_dir')


def install(home, *, project=None):
    """Add exact deny rules at the selected Claude Code scope, preserving other settings."""
    from .setup import Change, apply_changes, read_file

    path = ((Path(project) / '.claude/settings.local.json') if project else
            (Path(home) / '.claude/settings.json'))
    before = read_file(path)
    settings = json.loads(before) if before else {}
    if not isinstance(settings, dict):
        raise ValueError(f'Claude settings must be an object: {path}')
    permissions = settings.setdefault('permissions', {})
    if not isinstance(permissions, dict):
        raise ValueError(f'Claude permissions must be an object: {path}')
    deny = permissions.setdefault('deny', [])
    if not isinstance(deny, list) or any(not isinstance(rule, str) for rule in deny):
        raise ValueError(f'Claude deny rules must be a string array: {path}')
    for rule in HOST_ONLY:
        if rule not in deny:
            deny.append(rule)
    if before is None or json.loads(before) != settings:
        apply_changes([Change(path, before, (json.dumps(settings, indent=2) + '\n').encode())])
    return path
