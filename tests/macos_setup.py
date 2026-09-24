"""Exercise macOS Codex registration under a disposable home only.

Calls setup.configure directly so neither pwd nor a personal account home is
selected. It does not install the Chrome host or start a desktop provider.
"""

import argparse
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lcu.codex_hooks import original_hooks
from lcu.setup import configure, export_bundle, host_policy


def exercise(release: Path, app: Path) -> None:
    resources = app / 'Contents/Resources'
    modules = resources / 'cua_node/lib/node_modules'
    source = release / 'skills/lcu'
    runtime = release / 'bin/lcu'
    tools_root = release / 'agent-tools'
    with tempfile.TemporaryDirectory(prefix='lcu-macos-setup-', dir='/private/tmp') as temporary:
        home = Path(temporary)
        codex = home / '.codex/config.toml'
        codex.parent.mkdir()
        codex.write_text('# unrelated account settings\nmodel = "fixture-model"\n'
                         '[mcp_servers.unrelated]\ncommand = "fixture-command"\n')
        env = {
            'HOME': str(home), 'CODEX_HOME': str(codex.parent),
            'PATH': os.pathsep.join((str(Path(sys.executable).parent),
                                    str(resources / 'cua_node/bin'), '/usr/bin', '/bin')),
            'TMPDIR': str(home), 'LANG': 'C.UTF-8',
        }
        failures = configure(['codex'], home, source, [str(runtime)], tools_root,
                             release, environ=env)
        assert not failures, failures
        config = tomllib.loads(codex.read_text())
        assert config['model'] == 'fixture-model'
        assert config['mcp_servers']['unrelated']['command'] == 'fixture-command'
        registered = config['mcp_servers']['lcu']
        assert registered['command'] == str(runtime)
        for key, value in host_policy(release).items():
            assert registered[key] == value, key

        expected_hooks = original_hooks(resources / 'plugins/openai-bundled')
        assert set(expected_hooks) == {'Stop', 'Interrupt', 'SubagentStop'}
        for event, groups in expected_hooks.items():
            actual = config['hooks'][event]
            assert all(group in actual for group in groups), event
        assert config['hooks']['state'], 'Original hooks were not trusted'

        generated = home / '.local/share/lcu/skills/lcu'
        pairs = (
            (modules / '@oai/cua/docs/tinysky-alt-core-cua-repl.md',
             'references/upstream/cua/docs/tinysky-alt-core-cua-repl.md'),
            (modules / '@oai/cua-repl/instructions/macos/description.md',
             'references/upstream/cua-repl/instructions/macos/description.md'),
            (modules / '@oai/sky/docs/skills/oai_sky_lib/macos/SKILL.md',
             'references/upstream/sky/macos/SKILL.md'),
            (resources / 'plugins/openai-bundled/plugins/chrome/skills/control-chrome/SKILL.md',
             'references/upstream/chrome/skill/SKILL.md'),
        )
        for original, relative in pairs:
            assert (generated / relative).read_bytes() == original.read_bytes(), relative
        assert not (generated / 'references/upstream/cua-repl/instructions/linux').exists()
        assert not (generated / 'references/upstream/sky/linux').exists()
        installed_skills = [path for path in home.rglob('SKILL.md')
                            if path.parent.name == 'lcu' and path != generated / 'SKILL.md']
        assert installed_skills, 'Codex installer did not copy the full skill'
        assert any((path.parent / pairs[1][1]).is_file() for path in installed_skills)

        export = home / 'portable'
        export_bundle(export, source, [str(runtime)], release)
        assert json.loads((export / 'host-contract.json').read_text()) == host_policy(release)
        assert not (export / 'skills/lcu/references').exists()
        exported = b'\n'.join(path.read_bytes() for path in export.rglob('*') if path.is_file())
        assert (modules / '@oai/cua/docs/tinysky-alt-core-cua-repl.md').read_bytes() not in exported
        assert str(home).encode() not in exported
        assert str(runtime).encode() not in exported
    print(json.dumps({'result': 'passed', 'checks': [
        'disposable Codex registration', 'unrelated settings preserved',
        'original MCP policy', 'original trusted lifecycle hooks',
        'byte-identical macOS references', 'copied agent skill',
        'bootstrap-only portable export'], 'provider_actions': 0}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', type=Path, required=True)
    parser.add_argument('--app', type=Path, required=True)
    args = parser.parse_args()
    if platform.system() != 'Darwin':
        parser.error('This registration check requires macOS')
    exercise(args.release.resolve(strict=True), args.app.resolve(strict=True))


if __name__ == '__main__':
    main()
