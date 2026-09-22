"""Launch the original REPL with the installed Linux-only module set."""
import os
from pathlib import Path
import subprocess
import sys


def environment(root):
    runtime = root / 'runtime'
    env = dict(os.environ)
    # Do not inherit another installation's module roots, services, or startup code.
    for key in ('CUA_REPL_BROWSER_ENV', 'NODE_REPL_JS_BANNER', 'NODE_REPL_TRUSTED_SERVICES',
                'NODE_REPL_TOOL_OVERRIDES', 'NODE_OPTIONS', 'NODE_PATH',
                'OAI_SKY_CONFIG_PATH', 'OAI_SKY_LINUX_BIN'):
        env.pop(key, None)
    # Preserve caller sandbox, approval, request metadata, and model-check settings.
    env.update(
        PATH=str(runtime / 'bin') + ':' + env.get('PATH', '/usr/bin:/bin'),
        CUA_REPL_NODE_REPL_PATH=str(runtime / 'bin/node_repl'),
        CUA_REPL_ENABLED_SURFACES='computer',
        NODE_REPL_NODE_PATH=str(runtime / 'bin/node'),
        NODE_REPL_NODE_MODULE_DIRS=str(runtime / 'lib/node_modules'),
        NODE_REPL_TRUSTED_CODE_PATHS=str(runtime / 'lib/node_modules'),
        NODE_REPL_DISABLE_ANALYTICS='1',
    )
    return env


def main(root, argv):
    if argv[:1] in (['--help'], ['-h']):
        print('Usage: lcu [setup OPTIONS | doctor | --version]\nWith no arguments, starts the stdio MCP server.\nRun lcu setup --help for agent registration options.')
        return
    if argv[:1] == ['--version']:
        print('lcu 0.2.0 (Codex Linux runtime 0.0.16)')
        return
    if argv[:1] == ['setup']:
        from .setup import main as setup
        if '--prefix' not in argv:
            argv += ['--prefix', str(root.parent.parent)]
        setup(argv[1:])
        return
    if argv and argv != ['doctor']:
        raise ValueError('Usage: lcu [setup OPTIONS | doctor | --version]')
    runtime = root / 'runtime'
    env = environment(root)
    if argv == ['doctor']:
        if not env.get('DISPLAY') or not env.get('DBUS_SESSION_BUS_ADDRESS'):
            raise ValueError('A live X11 DISPLAY and DBUS_SESSION_BUS_ADDRESS are required. Use lcu-session or run inside the desktop session.')
        script = 'import {handleRpc} from "./lib/node_modules/@oai/sky/index.js"; const result = await handleRpc({type:"execute", method:"list_windows", args:[]}); console.log(JSON.stringify({windows:result}));'
        subprocess.run([str(runtime / 'bin/node'), '--input-type=module', '-e', script],
                       cwd=runtime, env=env, check=True, timeout=30)
        return
    launcher = runtime / 'lib/node_modules/@oai/cua-repl/index.js'
    script = 'const {launch} = await import(process.argv[1]); await launch();'
    os.execve(runtime / 'bin/node', [str(runtime / 'bin/node'), '--input-type=module', '-e', script, launcher.as_uri()], env)
