"""Launch the complete upstream Linux runtime without replacing its policies."""
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid


def environment(root):
    runtime = root / 'runtime'
    env = dict(os.environ)
    # Select our verified executables, while retaining upstream caller options,
    # metadata, services, policy flags, and additional module/trust roots.
    def prepend(key, *paths):
        return os.pathsep.join(dict.fromkeys([*(str(path) for path in paths),
            *(path for path in env.get(key, '').split(os.pathsep) if path)]))

    env.update(
        PATH=str(runtime / 'bin') + ':' + env.get('PATH', '/usr/bin:/bin'),
        CUA_REPL_NODE_REPL_PATH=str(runtime / 'bin/node_repl'),
        NODE_REPL_NODE_PATH=str(runtime / 'bin/node'),
        NODE_REPL_NODE_MODULE_DIRS=prepend('NODE_REPL_NODE_MODULE_DIRS', runtime / 'lib/node_modules'),
        NODE_REPL_TRUSTED_CODE_PATHS=prepend('NODE_REPL_TRUSTED_CODE_PATHS',
            runtime / 'lib/node_modules', root / 'host/plugins'),
    )
    env.setdefault('CUA_REPL_ENABLED_SURFACES', 'browser,computer')
    env.setdefault('CUA_REPL_BROWSER_ENV', 'codex-app')
    env.setdefault('CODEX_CLI_PATH', str(root / 'host/bin/codex'))
    # Fixed host defaults from nne/kie in the pinned application. The unified
    # codex-app surface is selected only with browserUseTinysky in original Lre.
    env.setdefault('NODE_REPL_NATIVE_PIPE_CONNECT_TIMEOUT_MS', '1000')
    if env['CUA_REPL_BROWSER_ENV'] == 'codex-app':
        env.setdefault('BROWSER_USE_TINYSKY_ENABLED', '1')
        flavor = env.get('BUILD_FLAVOR', '').strip()
        valid_flavors = ('dev', 'agent', 'nightly', 'internal-alpha', 'public-beta', 'prod')
        env.setdefault('BROWSER_USE_CODEX_APP_BUILD_FLAVOR', flavor if flavor in valid_flavors else 'prod')
        env.setdefault('BROWSER_USE_CODEX_APP_VERSION', '26.915.31945')
        # Unchanged Eie/Die strings from original main-DUHZj4_w.js (kie).
        backends = env.get('BROWSER_USE_AVAILABLE_BACKENDS', 'chrome,cdp,iab').split(',')
        if 'iab' in backends:
            env.setdefault('NODE_REPL_INSTRUCTIONS_USE_CASE_BROWSER',
                           'Control the in-app browser in conjunction with the Browser Plugin.')
        if 'chrome' in backends:
            env.setdefault('NODE_REPL_INSTRUCTIONS_USE_CASE_CHROME',
                           'Control the Chrome browser in conjunction with the Chrome Plugin. Prefer this method of controlling Chrome over alternatives (such as Computer Use) unless the user explicitly mentions an alternative.')
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
        print('Usage: lcu [--with-browser-host | setup OPTIONS | browser OPTIONS | doctor | --version]\nWith no arguments, starts the original stdio MCP server.\n--with-browser-host also owns the original in-app browser host for this MCP connection.\nRun lcu setup --help for agent registration options; lcu browser --help for browser connection setup.')
        return
    if argv[:1] == ['--version']:
        print('lcu 0.3.0-dev (Codex Linux runtime 0.0.16)')
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
    if argv and argv not in (['doctor'], ['--with-browser-host']):
        raise ValueError('Usage: lcu [--with-browser-host | setup OPTIONS | browser OPTIONS | doctor | --version]')
    runtime = root / 'runtime'
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
    surfaces = env['CUA_REPL_ENABLED_SURFACES'].split(',')
    backends = env.get('BROWSER_USE_AVAILABLE_BACKENDS', 'chrome,cdp,iab').split(',')
    if argv == ['--with-browser-host']:
        if 'browser' not in surfaces or env['CUA_REPL_BROWSER_ENV'] != 'codex-app' or 'iab' not in backends:
            raise ValueError('--with-browser-host requires the codex-app browser surface and iab backend.')
        from .host_bridge import run_mcp
        code = run_mcp(root, env, command)
        if code:
            raise ValueError(f'Original MCP runtime exited with status {code}.')
    else:
        os.execve(runtime / 'bin/node', command, env)
