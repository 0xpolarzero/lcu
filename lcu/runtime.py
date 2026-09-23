"""Launch the pinned application's original Linux computer-use provider."""
import json
import os
from pathlib import Path
import subprocess
import uuid


def paths(root):
    """Resolve one selected, intact application generation."""
    app = root / 'app'
    resources = app / 'resources'
    runtime = resources / 'cua_node'
    lock = json.loads((root / 'runtime.lock.json').read_text())
    descriptor = json.loads((root / 'installation.json').read_text())
    selected = Path(descriptor.get('app', ''))
    arch = descriptor.get('architecture')
    if (not selected or selected.is_absolute() or
            (root / selected).resolve() != app.resolve() or
            arch not in lock['architectures'] or
            descriptor.get('package_version') != lock['version'] or
            descriptor.get('sha256') != lock['architectures'][arch]['sha256']):
        raise ValueError('Selected application descriptor does not match the LCU lock and app link.')
    required = (
        runtime / 'bin/node', runtime / 'bin/node_repl',
        runtime / 'lib/node_modules/@oai/cua-repl/bin/cua-repl.mjs',
        resources / 'codex', resources / 'codex-code-mode-host',
        resources / 'plugins/openai-bundled/plugins/chrome/.codex-plugin/plugin.json',
        resources / 'plugins/openai-bundled/plugins/unified-computer-use/.mcp.json',
    )
    if not app.is_dir() or any(not path.is_file() for path in required):
        raise ValueError(f'Selected official application is incomplete: {app}. Rerun scripts/install.sh.')
    if any(not os.access(path, os.X_OK) for path in required[:2] + required[3:5]):
        raise ValueError(f'Selected official application has non-executable tools: {app}. Rerun scripts/install.sh.')
    manifest = json.loads((runtime / 'manifest.json').read_text())
    if (manifest.get('platform') != 'linux' or manifest.get('arch') != arch or
            manifest.get('runtime_archive_version') != lock['runtime']):
        raise ValueError('Selected application runtime does not match the LCU lock.')
    return app, resources, runtime, lock


def environment(root):
    _, resources, runtime, lock = paths(root)
    env = dict(os.environ)
    # Original gM/nne selects and trusts CODEX_HOME verbatim, including an
    # explicitly empty value. This changes only the launched child environment.
    if 'CODEX_HOME' not in env:
        home = env['HOME'] if 'HOME' in env else str(Path.home())
        selected = os.path.normpath(os.path.join(home, '.codex'))
        # Node path.join collapses double leading slashes on Linux.
        env['CODEX_HOME'] = '/' + selected.lstrip('/') if selected.startswith('//') else selected
    # Select our verified executables, while retaining upstream caller options,
    # metadata, services, policy flags, and additional module/trust roots.
    def prepend(key, *paths):
        return os.pathsep.join(dict.fromkeys([*(str(path) for path in paths if str(path)),
            *(path for path in env.get(key, '').split(os.pathsep) if path)]))

    env.update(
        PATH=str(runtime / 'bin') + ':' + env.get('PATH', '/usr/bin:/bin'),
        CUA_REPL_NODE_REPL_PATH=str(runtime / 'bin/node_repl'),
        NODE_REPL_NODE_PATH=str(runtime / 'bin/node'),
        NODE_REPL_NODE_MODULE_DIRS=prepend('NODE_REPL_NODE_MODULE_DIRS', runtime / 'lib/node_modules'),
        NODE_REPL_TRUSTED_CODE_PATHS=prepend('NODE_REPL_TRUSTED_CODE_PATHS',
            env['CODEX_HOME'], runtime / 'lib/node_modules', resources / 'plugins'),
    )
    env.setdefault('CUA_REPL_ENABLED_SURFACES', 'browser,computer')
    env.setdefault('CUA_REPL_BROWSER_ENV', 'codex-app')
    env.setdefault('CODEX_CLI_PATH', str(resources / 'codex'))
    # Fixed host defaults from nne/kie in the pinned application. The unified
    # codex-app surface is selected only with browserUseTinysky in original Lre.
    env.setdefault('NODE_REPL_NATIVE_PIPE_CONNECT_TIMEOUT_MS', '1000')
    if env['CUA_REPL_BROWSER_ENV'] == 'codex-app':
        env.setdefault('BROWSER_USE_AVAILABLE_BACKENDS', 'chrome')
        env.setdefault('BROWSER_USE_TINYSKY_ENABLED', '1')
        flavor = env.get('BUILD_FLAVOR', '').strip()
        valid_flavors = ('dev', 'agent', 'nightly', 'internal-alpha', 'public-beta', 'prod')
        env.setdefault('BROWSER_USE_CODEX_APP_BUILD_FLAVOR', flavor if flavor in valid_flavors else 'prod')
        env.setdefault('BROWSER_USE_CODEX_APP_VERSION', lock['version'])
    env.setdefault('NODE_REPL_DISABLE_ANALYTICS', '1')
    # Upstream browser routing needs an identity even for a generic MCP client.
    # This names this actual MCP connection, not a Codex model or an approval.
    # Host-supplied request metadata and per-call metadata keep precedence.
    if 'NODE_REPL_REQUEST_META' not in env:
        identity = 'lcu-' + str(uuid.uuid4())
        env['NODE_REPL_REQUEST_META'] = json.dumps({'x-codex-turn-metadata': {
            'session_id': identity, 'turn_id': identity + '-connection'}})
    return env


def main(root, argv):
    if argv[:1] in (['--help'], ['-h']):
        print('Usage: lcu [setup OPTIONS | browser install | doctor | --version]\n'
              'With no arguments, starts the original stdio MCP server.')
        return
    if argv[:1] == ['--version']:
        release_path = root / 'bundle.json'
        version = json.loads(release_path.read_text())['version'] if release_path.is_file() else 'source-checkout'
        lock = json.loads((root / 'runtime.lock.json').read_text())
        print(f"lcu {version} (ChatGPT Linux {lock['version']}; CUA {lock['runtime']})")
        return
    if argv[:1] == ['setup']:
        from .setup import main as setup
        if '--prefix' not in argv:
            argv += ['--prefix', str(root.parent.parent)]
        setup(argv[1:])
        return
    if argv[:1] == ['browser']:
        from .browser import main as browser
        browser(root, argv[1:])
        return
    if argv == ['--with-browser-host']:
        raise ValueError('--with-browser-host was removed with the embedded browser. '
                         'Run lcu browser install and enable the official Chrome extension.')
    if argv and argv != ['doctor']:
        raise ValueError('Usage: lcu [setup OPTIONS | browser install | doctor | --version]')
    _, _, runtime, _ = paths(root)
    env = environment(root)
    if argv == ['doctor']:
        if not env.get('DISPLAY') or not env.get('DBUS_SESSION_BUS_ADDRESS'):
            raise ValueError('A live X11 DISPLAY and DBUS_SESSION_BUS_ADDRESS are required. Use lcu-session or run inside the desktop session.')
        script = 'import {handleRpc} from "@oai/sky/service"; const result = await handleRpc({type:"execute", method:"list_windows", args:[]}); console.log(JSON.stringify({windows:result}));'
        subprocess.run([str(runtime / 'bin/node'), '--input-type=module', '-e', script],
                       cwd=runtime / 'lib', env=env, check=True, timeout=30)
        return
    launcher = runtime / 'lib/node_modules/@oai/cua-repl/bin/cua-repl.mjs'
    command = [str(runtime / 'bin/node'), str(launcher)]
    os.execve(runtime / 'bin/node', command, env)
