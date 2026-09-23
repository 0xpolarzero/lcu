#!/usr/bin/env python3
"""Install a versioned LCU runtime and optionally register agents."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

SOURCE = Path(__file__).resolve().parent.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(SOURCE))
from lcu import setup
from bundle import VERSION, architecture, verify
from installed_app import preflight as preflight_app, provision as provision_app


# Ubuntu 24.04 names for the pinned official application's Depends, plus LCU's
# X11/audio/session prerequisites. See docs/INSTALLATION.md for source mappings.
SYSTEM_PACKAGES = (
    'at-spi2-core', 'bubblewrap', 'ca-certificates', 'dbus-x11', 'ffmpeg',
    'libasound2t64', 'libatk-bridge2.0-0t64', 'libatk1.0-0t64', 'libatspi2.0-0t64',
    'libc6', 'libcairo2', 'libcups2t64', 'libdbus-1-3', 'libdrm2', 'libexpat1',
    'libgbm1', 'libgcc-s1', 'libgdk-pixbuf-2.0-0', 'libgl1', 'libglib2.0-bin',
    'libglib2.0-0t64', 'libgtk-3-0t64', 'libnotify4', 'libnspr4', 'libnss3',
    'libpango-1.0-0', 'libssl3t64', 'libstdc++6', 'libtss2-esys-3.0.2-0t64',
    'libtss2-mu-4.0.1-0t64', 'libtss2-tcti-device0t64', 'libudev1', 'libusb-1.0-0',
    'libx11-6', 'libx11-xcb1', 'libxcb-dri3-0', 'libxcb1', 'libxcomposite1',
    'libxdamage1', 'libxext6', 'libxfixes3', 'libxi6', 'libxkbcommon0', 'libxrandr2',
    'libxtst6', 'mesa-vulkan-drivers', 'pulseaudio', 'pulseaudio-utils', 'python3',
    'x11-utils', 'xdg-utils', 'xz-utils',
)


def checked_prefix(path):
    if not path.is_absolute():
        raise ValueError('The installation prefix must be absolute')
    path = setup.regular_path(path)
    if path.resolve().is_relative_to(SOURCE.resolve()):
        raise ValueError('Choose an installation prefix outside the extracted release bundle.')
    if not path.is_absolute() or len(path.parts) < 3 or path in (Path('/usr/local'), Path('/opt/lcu').parent):
        raise ValueError('Choose a dedicated absolute prefix, such as /opt/lcu.')
    if path.exists() and any(path.iterdir()) and not (path / '.lcu-install').is_file():
        raise ValueError('Installation prefix is not an existing LCU installation or an empty directory.')
    for name in ('.lcu-install', 'releases'):
        if (path / name).is_symlink():
            raise ValueError(f'Refusing a symlink at {path / name}')
    return path


def validate_release(release, account=None):
    user_options = {}
    env = dict(os.environ)
    if account is not None:
        env.update(HOME=account.pw_dir, USER=account.pw_name, LOGNAME=account.pw_name)
        user_options['cwd'] = account.pw_dir
        if os.getuid() == 0 and account.pw_uid != 0:
            user_options.update(user=account.pw_uid, group=account.pw_gid,
                                extra_groups=os.getgrouplist(account.pw_name, account.pw_gid))
        elif os.getuid() != account.pw_uid:
            raise ValueError(f'Cannot validate the installation as {account.pw_name} from this account')
    subprocess.run([str(release / 'bin/lcu'), '--version'], check=True, timeout=20,
                   env=env, **user_options)
    runtime = release / 'app/resources/cua_node'
    subprocess.run([str(runtime / 'bin/node_repl'), '--help'], check=True, timeout=20,
                   stdout=subprocess.DEVNULL, env=env, **user_options)
    env['NODE_REPL_DISABLE_ANALYTICS'] = '1'
    subprocess.run([str(runtime / 'bin/node'), '--input-type=module', '-e',
                    'const s = await import(process.argv[1]); const r = await s.handleRpc({type:"setup"}); if(r.target!=="linux") throw Error("Wrong platform");',
                    (runtime / 'lib/node_modules/@oai/sky/dist/project/cua/sky_js/src/service.js').as_uri()], env=env,
                   check=True, timeout=20, **user_options)


def install(prefix, *, app_package=None, existing_app=None, offline=False, account=None):
    prefix = checked_prefix(prefix)
    arch = architecture()
    verify(SOURCE, arch)
    prefix.mkdir(parents=True, exist_ok=True)
    application, generation = provision_app(prefix, arch, package=app_package,
                                           existing_app=existing_app, offline=offline, root=SOURCE,
                                           account=account)
    with (prefix / '.lcu-install').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        releases = prefix / 'releases'
        releases.mkdir(exist_ok=True)
        release = releases / (VERSION + '-' + uuid.uuid4().hex[:12])
        release.mkdir(mode=0o755)
        try:
            shutil.copytree(SOURCE, release, dirs_exist_ok=True, symlinks=True)
            verify(release, arch)
            app_relative = os.path.relpath(application, release)
            (release / 'app').symlink_to(app_relative, target_is_directory=True)
            lock_data = json.loads((SOURCE / 'runtime.lock.json').read_text())
            app_entry = lock_data['architectures'][arch]
            (release / 'installation.json').write_text(json.dumps({
                'package_version': lock_data['version'], 'architecture': arch,
                'sha256': app_entry['sha256'], 'app': app_relative,
            }, indent=2) + '\n')
            validate_release(release, account)
            current = prefix / 'current'
            if current.exists() and not current.is_symlink():
                raise ValueError('Refusing to replace a non-symlink current path')
            temporary_link = prefix / '.next'
            if temporary_link.exists() or temporary_link.is_symlink():
                raise ValueError('Unexpected .next path; inspect the installation before retrying')
            temporary_link.symlink_to(release.relative_to(prefix))
            os.replace(temporary_link, current)
        except BaseException:
            shutil.rmtree(release)
            raise
    return release


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    legacy = bool(argv and not argv[0].startswith('-'))
    if legacy:
        argv = ['--prefix', argv[0], *argv[1:]]
    parser = setup.parser()
    parser.description = __doc__ + ' Requires Linux, Python 3.12+, X11 and D-Bus; apt system provisioning requires root.'
    parser.add_argument('--runtime-only', action='store_true', help='Install without registering an agent')
    parser.add_argument('--skip-system', action='store_true', help='Skip apt; system libraries must already exist')
    parser.add_argument('--app-package', type=Path, help='Local official pinned ChatGPT .deb')
    parser.add_argument('--existing-app', type=Path, help='Use an existing compatible complete ChatGPT application directory')
    parser.add_argument('--offline', action='store_true', help='Never use the network; requires --skip-system and preinstalled system libraries')
    args = parser.parse_args(argv)
    if args.list_agents:
        setup.main(['--list-agents'])
        return
    if args.offline and not args.skip_system:
        raise ValueError('--offline requires --skip-system; provision system libraries before an offline install')
    if sys.version_info < (3, 12):
        raise ValueError('Python 3.12 or later is required')
    arch = architecture()
    if legacy and not args.agent and not args.export:
        args.runtime_only = True
    account, names = setup.validate(args)
    prefix = checked_prefix(args.prefix)
    if args.runtime_only:
        if args.agent or args.export or args.project or args.scope != 'user' or args.check_desktop or args.session != 'discover' or args.browser_host:
            raise ValueError('--runtime-only cannot include agent setup options')
    elif not names and not args.export and (args.yes or not sys.stdin.isatty()):
        raise ValueError('Select --agent NAME, --agent all, --agent auto, --export PATH, or --runtime-only')
    if not args.runtime_only:
        setup.installer_environment(Path(account.pw_dir), names, {} if os.getuid() == 0 and account.pw_uid else os.environ)
    # Refuse absent, corrupt, or wrong-architecture payloads before apt or any writes.
    verify(SOURCE, arch)
    preflight_app(prefix, arch, package=args.app_package, existing_app=args.existing_app,
                  offline=args.offline, root=SOURCE, account=account)
    if not args.skip_system:
        if os.getuid() != 0 or not shutil.which('apt-get'):
            raise ValueError('Automatic system provisioning requires root and apt-get; otherwise provision dependencies and use --skip-system')
        subprocess.run(['apt-get', 'update'], check=True)
        subprocess.run(['apt-get', 'install', '-y', *SYSTEM_PACKAGES], check=True)
    install(prefix, app_package=args.app_package, existing_app=args.existing_app,
            offline=args.offline, account=account)
    print(f'LCU installed: {prefix}/current/bin/lcu')
    if not args.runtime_only:
        forwarded = ['--prefix', str(prefix), '--user', account.pw_name, '--scope', args.scope, '--session', args.session]
        for name in args.agent:
            forwarded += ['--agent', name]
        for flag in ('project', 'export'):
            if getattr(args, flag):
                forwarded += ['--' + flag, str(getattr(args, flag))]
        for flag in ('yes', 'check_desktop'):
            if getattr(args, flag):
                forwarded += ['--' + flag.replace('_', '-')]
        # Run setup from the selected release, and drop privileges before account writes.
        subprocess.run([str(prefix / 'current/bin/lcu'), 'setup', *forwarded], check=True)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        sys.exit(f'LCU installer: {exc}')
