"""Install the original Codex turn lifecycle records using its own config writer."""
import copy
import json
from pathlib import Path
import tempfile
import tomllib


def original_plugin(host_root):
    return Path(host_root) / 'plugins/unified-computer-use'


def original_hooks(host_root):
    manifest = json.loads((original_plugin(host_root) / '.codex-plugin/plugin.json').read_text())
    events = manifest['hooks']['hooks']
    if set(events) != {'Stop', 'Interrupt', 'SubagentStop'}:
        raise ValueError('Upstream lifecycle events changed; review before installation.')
    for groups in events.values():
        for group in groups:
            for hook in group['hooks']:
                if hook['type'] != 'mcp_tool' or hook['server'] != 'cua_repl' or hook['tool'] != 'turn_ended':
                    raise ValueError('Upstream lifecycle contract changed; review before installation.')
                hook['server'] = 'lcu'
    return events


def export_files(command, host_root):
    """Native plugin files; exported skills live at the standard ./skills path."""
    original = original_plugin(host_root)
    manifest = json.loads((original / '.codex-plugin/plugin.json').read_text())
    manifest.update(name='lcu', description='Computer use for AI agents on Linux.', skills='./skills')
    manifest['hooks']['hooks'] = original_hooks(host_root)
    descriptor = json.loads((original / '.mcp.json').read_text())
    server = descriptor['mcpServers'].pop('cua_repl')
    server.update(command=command[0], args=command[1:], enabled=True)
    descriptor['mcpServers']['lcu'] = server
    contract = {
        'hooks': manifest['hooks']['hooks'],
        'requestMetadata': 'Forward each real session_id and turn_id as x-codex-turn-metadata in MCP request _meta.',
        'lifecycle': 'Call lcu.turn_ended when the host stops or interrupts a turn, including a subagent turn; substitute the original hook input variables with real host identifiers. Keep the MCP connection alive until cleanup finishes.',
        'unsupportedHosts': 'Installing MCP and a skill alone does not supply turn lifecycle hooks. A host without equivalent hooks must implement this contract before claiming Codex lifecycle parity.',
        'codexTrust': 'Codex requires trust for these exact hooks. Use lcu setup --agent codex or review and trust them in Codex; this export does not bypass hook trust.',
    }
    return {name: (json.dumps(value, indent=2) + '\n').encode() for name, value in (
        ('.codex-plugin/plugin.json', manifest), ('.mcp.json', descriptor),
        ('lifecycle-contract.json', contract))}


from .app_server import app_server as config_writer


def install_hooks(cli, config_path, cwd, env, host_root):
    """Preserve scope and unrelated hooks; trust only the reviewed original records.

    The pinned native API writes user config only. A disposable CODEX_HOME lets
    it edit either target scope without creating CLI state in the user's project.
    Commit the target config and exact per-hook trust through concurrent-edit
    guards. Project hook trust is stored in the selected user config.
    """
    from .setup import Change, apply_changes, read_file, regular_path
    config_path = regular_path(config_path)
    before = read_file(config_path)
    current = tomllib.loads((before or b'').decode())
    trust_path = regular_path(Path(env.get('CODEX_HOME') or Path(env['HOME']) / '.codex') / 'config.toml')
    trust_before = before if trust_path == config_path else read_file(trust_path)
    tomllib.loads((trust_before or b'').decode())
    hooks = copy.deepcopy(current.get('hooks', {}))
    expected = original_hooks(host_root)
    for event, original in expected.items():
        groups = hooks.setdefault(event, [])
        if not isinstance(groups, list):
            raise ValueError(f'Invalid existing Codex hook list: {event}')
        for group in groups:
            if any(h.get('server') == 'lcu' and h.get('tool') == 'turn_ended' for h in group.get('hooks', [])) and group not in original:
                raise ValueError(f'Existing LCU {event} hook differs from upstream; review it before setup.')
        for group in original:
            if group not in groups:
                groups.append(group)
    with tempfile.TemporaryDirectory(prefix='lcu-codex-config-') as temporary:
        scratch = Path(temporary)
        config = scratch / 'config.toml'
        config.write_bytes(before or b'')
        # The scratch home keeps account credentials and project layers out of
        # this configuration-only process. No model turn or hook is executed.
        isolated = {**env, 'HOME': temporary, 'CODEX_HOME': temporary}
        with config_writer(cli, scratch, isolated) as call:
            edits = [{'keyPath': 'hooks.' + event, 'value': hooks[event], 'mergeStrategy': 'replace'} for event in expected]
            call('config/batchWrite', {'edits': edits})
            # Match the exact source path; unrelated/plugin hooks are not trusted.
            listed = call('hooks/list', {'cwds': [temporary]})
            trust = []
            for entry in listed['data']:
                if entry['errors']:
                    raise ValueError('Codex could not read lifecycle hooks: ' + json.dumps(entry['errors']))
                for hook in entry['hooks']:
                    if hook['sourcePath'] == str(config) and hook.get('eventName') in {'stop', 'interrupt', 'subagentStop'} and hook.get('server') == 'lcu' and hook.get('tool') == 'turn_ended':
                        suffix = hook['key'].removeprefix(str(config))
                        if suffix == hook['key']:
                            raise ValueError('Upstream hook key format changed.')
                        key = str(config_path) + suffix
                        trust.append({'keyPath': 'hooks.state.' + json.dumps(key) + '.trusted_hash',
                                      'value': hook['currentHash'], 'mergeStrategy': 'replace'})
            if len(trust) != sum(len(g['hooks']) for groups in expected.values() for g in groups):
                raise ValueError('Codex did not discover exactly the original LCU lifecycle hooks.')
            after = config.read_bytes()
            if trust_path != config_path:
                # Native Codex ignores project-provided hook trust. Store only
                # these path-specific approvals in the real user's config.
                config.write_bytes(trust_before or b'')
            call('config/batchWrite', {'edits': trust})
        trusted = config.read_bytes()
    changes = [Change(config_path, before, trusted if trust_path == config_path else after)]
    if trust_path != config_path:
        changes.append(Change(trust_path, trust_before, trusted))
    apply_changes(changes)
    return config_path
