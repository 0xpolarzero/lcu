"""Connect installed Chromium browsers using OpenAI's original native host."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def install(root, directory=None):
    from .runtime import environment

    # `app` is the installed complete application, including its original
    # plugin resources. Resolve through it so packaged layouts do not need a
    # second mutable plugin tree beside the sealed application.
    source = root / 'app/resources/plugins/openai-bundled/plugins/chrome'
    # The upstream installer writes its host configuration beside the executable.
    # Keep the sealed release immutable; give this account a private host copy.
    data = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
    selected_app = (root / 'app').resolve()
    identity = hashlib.sha256(str(selected_app).encode()).hexdigest()[:16]
    destination = Path(directory).expanduser().absolute() if directory else data / 'lcu/browser' / identity
    marker = destination / '.lcu-browser-host'
    expected = str(selected_app) + '\n'
    if destination.is_symlink():
        raise ValueError('The browser host directory must not be a symlink.')
    if destination.exists():
        if not marker.is_file() or marker.is_symlink() or marker.read_text() != expected:
            raise ValueError('The browser host directory belongs to another installation; select an empty directory.')
        installed_plugin = destination / 'chrome'
        if not (installed_plugin / 'scripts/installManifest.mjs').is_file():
            raise ValueError('The private browser host copy is incomplete or corrupt; remove it and run `lcu browser install` again.')
    else:
        if not (source / 'scripts/installManifest.mjs').is_file():
            raise ValueError('The complete upstream Chrome plugin is missing from this bundle.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        scratch = Path(tempfile.mkdtemp(prefix='.lcu-browser-', dir=destination.parent))
        try:
            shutil.copytree(source, scratch / 'chrome', symlinks=True)
            (scratch / '.lcu-browser-host').write_text(expected)
            scratch.rename(destination)
        finally:
            if scratch.exists():
                shutil.rmtree(scratch)
    relay_source = root / 'lcu/native_host.py'
    if not relay_source.is_file():
        raise ValueError('The LCU Chrome native-host relay is missing from this release.')
    relay = destination / 'lcu-native-host'
    with tempfile.NamedTemporaryFile(dir=destination, prefix='.lcu-native-host-', delete=False) as staged:
        staged_path = Path(staged.name)
    try:
        shutil.copyfile(relay_source, staged_path)
        staged_path.chmod(0o700)
        staged_path.replace(relay)
    finally:
        staged_path.unlink(missing_ok=True)
    env = environment(root)
    script = ('const {install} = await import(process.argv[1]); '
              'await install({appServerRuntimePaths:{codexCliPath:process.env.CODEX_CLI_PATH,'
              'nodePath:process.env.NODE_REPL_NODE_PATH,nodeReplPath:process.env.CUA_REPL_NODE_REPL_PATH}});')
    subprocess.run([env['NODE_REPL_NODE_PATH'], '--input-type=module', '-e', script,
                    (destination / 'chrome/scripts/installManifest.mjs').as_uri()],
                   env=env, check=True, capture_output=True)
    # The pinned original installer returns no manifest list. Locate only its
    # native-host manifest name at the documented config depths, then require
    # each candidate to point at this selected private copy before changing it.
    config_roots = {Path(env.get('HOME', Path.home())) / '.config'}
    for key in ('XDG_CONFIG_HOME', 'CHROME_CONFIG_HOME'):
        if env.get(key):
            config_roots.add(Path(env[key]))
    manifest_paths = set()
    name = 'com.openai.codexextension.json'
    for config_root in config_roots:
        manifest_paths.update(config_root.glob(f'*/NativeMessagingHosts/{name}'))
        manifest_paths.update(config_root.glob(f'*/*/NativeMessagingHosts/{name}'))
    changed = 0
    for manifest_path in sorted(manifest_paths):
        if manifest_path.is_symlink():
            raise ValueError(f'Native-host manifest must be a regular file: {manifest_path}')
        manifest = json.loads(manifest_path.read_text())
        original = Path(manifest.get('path', ''))
        if (original.name != 'extension-host' or
                not original.resolve().is_relative_to((destination / 'chrome/extension-host').resolve())):
            continue
        manifest['path'] = str(relay)
        with tempfile.NamedTemporaryFile(mode='w', dir=manifest_path.parent,
                                         prefix='.lcu-manifest-', delete=False) as staged:
            staged_path = Path(staged.name)
            json.dump(manifest, staged, indent=2)
            staged.write('\n')
        try:
            staged_path.chmod(0o644)
            staged_path.replace(manifest_path)
        finally:
            staged_path.unlink(missing_ok=True)
        changed += 1
    if changed == 0:
        raise ValueError('The original Chrome installer produced no manifest for the selected host.')
    return destination


def main(root, argv):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='action', required=True)
    setup = subparsers.add_parser('install', help='Install the original native host for the current Linux account')
    setup.add_argument('--directory', type=Path, help='Private writable host directory (default: XDG data directory)')
    if argv[:1] in (['serve'], ['protocol']):
        parser.error('the in-app browser host and codex:// protocol commands were removed; use the installed app browser. For external Chrome, run `lcu browser install` and enable the official ChatGPT extension.')
    args = parser.parse_args(argv)
    destination = install(root, args.directory)
    print(f'LCU browser native host configured: {destination}')
    print('Install or enable the official ChatGPT browser extension in the browser you want to use.')
    print('The extension and browser must run under this same Linux account. See docs/INSTALLATION.md.')
