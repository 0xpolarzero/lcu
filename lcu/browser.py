"""Connect installed Chromium browsers using OpenAI's original native host."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def install(root, directory=None):
    from .runtime import environment

    source = root / 'host/plugins/chrome'
    if not (source / 'scripts/installManifest.mjs').is_file():
        raise ValueError('The complete upstream Chrome plugin is missing from this bundle.')
    # The upstream installer writes its host configuration beside the executable.
    # Keep the sealed release immutable; give this account a private host copy.
    data = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
    identity = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
    destination = Path(directory).expanduser().absolute() if directory else data / 'lcu/browser' / identity
    marker = destination / '.lcu-browser-host'
    expected = str(root.resolve()) + '\n'
    if destination.is_symlink():
        raise ValueError('The browser host directory must not be a symlink.')
    if destination.exists():
        if not marker.is_file() or marker.is_symlink() or marker.read_text() != expected:
            raise ValueError('The browser host directory belongs to another installation; select an empty directory.')
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        scratch = Path(tempfile.mkdtemp(prefix='.lcu-browser-', dir=destination.parent))
        try:
            shutil.copytree(source, scratch / 'chrome', symlinks=True)
            (scratch / '.lcu-browser-host').write_text(expected)
            scratch.rename(destination)
        finally:
            if scratch.exists():
                shutil.rmtree(scratch)
    env = environment(root)
    script = ('const {install} = await import(process.argv[1]); '
              'await install({appServerRuntimePaths:{codexCliPath:process.env.CODEX_CLI_PATH,'
              'nodePath:process.env.NODE_REPL_NODE_PATH,nodeReplPath:process.env.CUA_REPL_NODE_REPL_PATH}});')
    subprocess.run([env['NODE_REPL_NODE_PATH'], '--input-type=module', '-e', script,
                    (destination / 'chrome/scripts/installManifest.mjs').as_uri()],
                   env=env, check=True)
    return destination


def main(root, argv):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='action', required=True)
    setup = subparsers.add_parser('install', help='Install the original native host for the current Linux account')
    setup.add_argument('--directory', type=Path, help='Private writable host directory (default: XDG data directory)')
    host = subparsers.add_parser('serve', help='Run the original in-app browser host for an actual agent session')
    host.add_argument('--session-id', required=True, help='Actual session_id supplied in MCP request metadata')
    protocol = subparsers.add_parser('protocol', help='Opt-in codex:// delivery to one live session owner')
    protocol_commands = protocol.add_subparsers(dest='protocol_action', required=True)
    handler = protocol_commands.add_parser('install', help='Create a session-specific desktop handler without changing the default')
    handler.add_argument('--session-id', required=True, help='Actual session_id of the intended owner')
    handler.add_argument('--set-default', action='store_true', help='Explicitly make this handler the current codex:// default')
    delivery = protocol_commands.add_parser('deliver', help='Forward an OS callback to its selected live owner')
    delivery.add_argument('--session-key', required=True, help=argparse.SUPPRESS)
    delivery.add_argument('url', help='codex:// URL supplied by the desktop handler')
    args = parser.parse_args(argv)
    if args.action == 'serve':
        from .host_bridge import serve
        from .runtime import environment
        serve(root, environment(root), args.session_id)
        return
    if args.action == 'protocol':
        from .protocol import decode_session_key, deliver, install_handler
        if args.protocol_action == 'install':
            destination = install_handler(root, args.session_id, set_default=args.set_default)
            print(f'Codex protocol handler written: {destination}')
            if not args.set_default:
                print(f'To select it explicitly: xdg-mime default {destination.name} x-scheme-handler/codex')
        else:
            deliver(decode_session_key(args.session_key), args.url)
            print('Original owner queue accepted the callback; OAuth completion is not implied.')
        return
    destination = install(root, args.directory)
    print(f'Original browser native host configured: {destination}')
    print('Install or enable the official ChatGPT browser extension in the browser you want to use.')
    print('The extension and browser must run under this same Linux account. See docs/BROWSER-HOST-PARITY.md.')
