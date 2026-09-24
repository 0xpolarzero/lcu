"""Launch the selected application's original computer-use provider."""
import json
import ntpath
import os
from pathlib import Path
import subprocess
import sys
import uuid

USAGE = ('Usage: lcu [--chrome] [--mcp-discovery-compat]\n'
         '       lcu setup OPTIONS\n'
         '       lcu browser install\n'
         '       lcu browser status\n'
         '       lcu doctor\n'
         '       lcu --version')


def paths(root):
    """Resolve one selected, intact application generation."""
    app = root / 'app'
    resources = app / 'resources'
    runtime = resources / 'cua_node'
    lock = json.loads((root / 'runtime.lock.json').read_text())
    descriptor = json.loads((root / 'installation.json').read_text())
    selected = Path(descriptor.get('app', ''))
    arch = descriptor.get('architecture')
    target = descriptor.get('platform', 'linux')
    if target == 'darwin':
        policy = lock.get('platforms', {}).get('darwin', {})
        entry = policy.get('architectures', {}).get(arch)
        if (not selected.is_absolute() or not entry or
                selected.resolve() != app.resolve() or
                descriptor.get('package_version') != policy.get('version') or
                descriptor.get('runtime') != policy.get('runtime')):
            raise ValueError('Selected application descriptor does not match the macOS lock and app link.')
        from .platforms import resolve_installed_mac_app
        resolved = resolve_installed_mac_app(selected,
            expected_version=policy['version'], expected_runtime=policy['runtime'],
            expected_hashes=entry['components'], arch=arch)
        return resolved.app, resolved.resources, resolved.runtime, policy
    if target == 'windows':
        policy = lock.get('platforms', {}).get('windows', {})
        entry = policy.get('architectures', {}).get(arch)
        if (not selected.is_absolute() or arch != 'x64' or not entry or
                descriptor.get('package_version') != policy.get('version') or
                descriptor.get('runtime') != policy.get('runtime') or
                descriptor.get('sha256') != entry.get('sha256')):
            raise ValueError('Selected application descriptor does not match the Windows lock.')
        prefix = root.parent.parent
        apps = prefix / 'apps'
        generation = apps / f"{policy['version']}-x64-{entry['sha256'][:16]}"
        expected = generation / 'app'
        if (selected != expected or any(path.is_symlink() or path.is_junction()
                                        for path in (apps, generation, selected))):
            raise ValueError('Selected Windows application is not the managed private generation.')
        from .windows import validate_windows_app_tree
        resolved = validate_windows_app_tree(selected,
            expected_version=policy['version'], expected_runtime=policy['runtime'],
            expected_hashes=entry['components'])
        if resolved.app != expected.resolve(strict=True):
            raise ValueError('Selected Windows application does not match the managed generation.')
        return resolved.app, resolved.resources, resolved.runtime, policy
    if target != 'linux':
        raise ValueError(f'Unsupported installed application platform: {target}')
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


def environment(root, resolved=None, *, chrome=False):
    _, resources, runtime, lock = resolved or paths(root)
    target = json.loads((root / 'installation.json').read_text()).get('platform', 'linux')
    windows = target == 'windows'
    path_api = ntpath if windows else os.path
    separator = ';' if windows else os.pathsep
    module_dir = runtime / ('bin/node_modules' if windows else 'lib/node_modules')
    node = runtime / ('bin/node.exe' if windows else 'bin/node')
    node_repl = runtime / ('bin/node_repl.exe' if windows else 'bin/node_repl')
    codex = resources / ('codex.exe' if windows else 'codex')
    env = dict(os.environ)
    # Original gM/nne selects and trusts CODEX_HOME verbatim, including an
    # explicitly empty value. This changes only the launched child environment.
    if 'CODEX_HOME' not in env:
        home = (env.get('USERPROFILE') or env.get('HOME') or str(Path.home())) if windows else (
            env['HOME'] if 'HOME' in env else str(Path.home()))
        selected = path_api.normpath(path_api.join(home, '.codex'))
        # Node path.join collapses double leading slashes on Linux.
        env['CODEX_HOME'] = ('/' + selected.lstrip('/') if selected.startswith('//') else selected)
    # Select our verified executables, while retaining upstream caller options,
    # metadata, services, policy flags, and additional module/trust roots.
    def prepend(key, *paths):
        return separator.join(dict.fromkeys([*(str(path) for path in paths if str(path)),
            *(path for path in env.get(key, '').split(separator) if path)]))

    if windows:
        existing_path = next((value for key, value in env.items() if key.upper() == 'PATH'), '')
        for key in tuple(env):
            if key.upper() == 'PATH':
                del env[key]
    else:
        existing_path = env.get('PATH', '/usr/bin:/bin')

    env.update(
        PATH=str(runtime / 'bin') + separator + existing_path,
        CUA_REPL_NODE_REPL_PATH=str(node_repl),
        NODE_REPL_NODE_PATH=str(node),
        NODE_REPL_NODE_MODULE_DIRS=prepend('NODE_REPL_NODE_MODULE_DIRS', module_dir),
        NODE_REPL_TRUSTED_CODE_PATHS=prepend('NODE_REPL_TRUSTED_CODE_PATHS',
            env['CODEX_HOME'], module_dir, resources / 'plugins'),
    )
    # The original launcher selects both its API and instructions from this
    # surface list. External Chrome is an explicit opt-in for LCU clients.
    env.setdefault('CUA_REPL_ENABLED_SURFACES', 'browser,computer' if chrome else 'computer')
    env.setdefault('CUA_REPL_BROWSER_ENV', 'codex-app')
    env.setdefault('CODEX_CLI_PATH', str(codex))
    if resources.parent.name == 'Contents':
        # Original Sky's macOS native-pipe transport uses this signed helper
        # through LaunchServices when no existing CUA service is connected.
        env.setdefault('SKY_CUA_SERVICE_PATH', str(runtime / 'lib/node_modules/@oai/sky/Codex Computer Use.app'))
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
    # Original browser service switch: do not initialize account identity or
    # telemetry. The relay already supplies the local agent-header decision.
    env.setdefault('BROWSER_USE_DISABLE_AMBIENT_NETWORK', '1')
    # Upstream browser routing needs an identity even for a generic MCP client.
    # This names this actual MCP connection, not a Codex model or an approval.
    # Host-supplied request metadata and per-call metadata keep precedence.
    if 'NODE_REPL_REQUEST_META' not in env:
        identity = 'lcu-' + str(uuid.uuid4())
        env['NODE_REPL_REQUEST_META'] = json.dumps({'x-codex-turn-metadata': {
            'session_id': identity, 'turn_id': identity + '-connection'}})
    return env


def reply_to_server_discover(source, destination):
    """Return a legacy-version probe error without reading beyond its line."""
    raw = bytearray()
    while len(raw) <= 1024 * 1024:
        byte = source.read(1)
        if not byte:
            break
        raw.extend(byte)
        if byte == b'\n':
            break
    if not raw.endswith(b'\n'):
        raise ValueError('Expected a newline-terminated initial JSON-RPC server/discover request.')
    if len(raw) > 1024 * 1024:
        raise ValueError('Initial JSON-RPC server/discover request exceeds 1 MiB.')
    try:
        request = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError('Expected a valid initial JSON-RPC server/discover request.') from exc
    request_id = request.get('id') if isinstance(request, dict) else None
    if (not isinstance(request, dict) or request.get('jsonrpc') != '2.0' or
            request.get('method') != 'server/discover' or
            isinstance(request_id, bool) or not isinstance(request_id, (str, int, float))):
        raise ValueError('Expected an initial JSON-RPC server/discover request in compatibility mode.')
    response = {'jsonrpc': '2.0', 'id': request_id,
                'error': {'code': -32601, 'message': 'Method not found'}}
    destination.write((json.dumps(response, separators=(',', ':')) + '\n').encode())
    destination.flush()


def main(root, argv):
    # Agent registrations place --chrome before generic executable probes.
    if argv[:1] == ['--chrome'] and argv[1:] in (['--help'], ['-h'], ['--version']):
        argv = argv[1:]
    if argv[:1] in (['--help'], ['-h']):
        print(USAGE + '\nWith no arguments, starts the original computer-use stdio MCP server. '
              '`lcu --chrome` also enables its browser surface; `lcu setup --chrome` registers that command.')
        return
    if argv[:1] == ['--version']:
        release_path = root / 'bundle.json'
        version = json.loads(release_path.read_text())['version'] if release_path.is_file() else 'source-checkout'
        lock = json.loads((root / 'runtime.lock.json').read_text())
        descriptor_path = root / 'installation.json'
        descriptor = json.loads(descriptor_path.read_text()) if descriptor_path.is_file() else {}
        target = descriptor.get('platform', 'linux')
        policy = lock.get('platforms', {}).get(target, lock)
        print(f"lcu {version} (ChatGPT {target} {policy['version']}; CUA {policy['runtime']})")
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
    chrome = argv.count('--chrome') == 1
    direct_args = [arg for arg in argv if arg != '--chrome']
    discovery_compat = direct_args == ['--mcp-discovery-compat']
    if argv.count('--chrome') > 1 or direct_args not in ([], ['doctor'], ['--mcp-discovery-compat']):
        raise ValueError(USAGE)
    resolved = paths(root)
    app, resources, runtime, _ = resolved
    env = environment(root, resolved, chrome=chrome)
    windows = json.loads((root / 'installation.json').read_text()).get('platform') == 'windows'
    if direct_args == ['doctor']:
        if not windows and resources.parent.name != 'Contents' and (not env.get('DISPLAY') or not env.get('DBUS_SESSION_BUS_ADDRESS')):
            raise ValueError('A live X11 DISPLAY and DBUS_SESSION_BUS_ADDRESS are required. Use lcu-session or run inside the desktop session.')
        script = 'import {handleRpc} from "@oai/sky/service"; const result = await handleRpc({type:"execute", method:"list_windows", args:[]}); console.log(JSON.stringify({windows:result}));'
        subprocess.run([env['NODE_REPL_NODE_PATH'], '--input-type=module', '-e', script],
                       cwd=runtime / ('bin' if windows else 'lib'), env=env, check=True, timeout=30)
        return
    if windows:
        from .windows import _component
        launcher = _component(resources.parents[1],
            'app/resources/cua_node/bin/node_modules/@oai/cua-repl/bin/cua-repl.mjs')
    else:
        launcher = runtime / 'lib/node_modules/@oai/cua-repl/bin/cua-repl.mjs'
    command = [env['NODE_REPL_NODE_PATH'], str(launcher)]
    if discovery_compat:
        reply_to_server_discover(sys.stdin.buffer.raw, sys.stdout.buffer)
    if windows:
        from .windows_host import start_original_host, stop_original_host
        helper = _component(app,
            'app/resources/cua_node/bin/node_modules/@oai/sky/bin/windows/codex-computer-use.exe')
        transport = _component(app,
            'app/resources/cua_node/bin/node_modules/@oai/sky/dist/project/cua/sky_js/src/targets/windows/internal/helper_transport.js')
        host, pipe = start_original_host(
            node=Path(env['NODE_REPL_NODE_PATH']), entry=root / 'lcu-host/windows-pipe-host.cjs',
            helper=helper, transport=transport, env=env)
        env['SKY_CUA_NATIVE_PIPE'] = '1'
        env['SKY_CUA_NATIVE_PIPE_DIRECTORY'] = pipe
        try:
            status = subprocess.run(command, env=env, check=False).returncode
        finally:
            stop_original_host(host)
        raise SystemExit(status)
    os.execve(runtime / 'bin/node', command, env)
