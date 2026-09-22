#!/usr/bin/env python3
"""Install a versioned Cual runtime and optionally register agents."""
import argparse
import fcntl
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import uuid

SOURCE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SOURCE))
from cual import setup
from project_runtime import provision
from provision_agent_tools import provision as provision_agents


def checked_prefix(path):
    if not path.is_absolute():
        raise ValueError('The installation prefix must be absolute')
    path = setup.regular_path(path)
    if not path.is_absolute() or len(path.parts) < 3 or path in (Path('/usr/local'), Path('/opt/cual').parent):
        raise ValueError('Choose a dedicated absolute prefix, such as /opt/cual.')
    if path.exists() and any(path.iterdir()) and not (path / '.cual-install').is_file():
        raise ValueError('Installation prefix is not an existing Cual installation or an empty directory.')
    for name in ('.cual-install', 'releases'):
        if (path / name).is_symlink():
            raise ValueError(f'Refusing a symlink at {path / name}')
    return path


def install(prefix, package=None):
    arch = {'aarch64': 'arm64', 'arm64': 'arm64', 'x86_64': 'x64', 'amd64': 'x64'}.get(platform.machine())
    if platform.system() != 'Linux' or arch is None:
        raise ValueError('Cual requires Linux ARM64 or x86-64.')
    prefix.mkdir(parents=True, exist_ok=True)
    with (prefix / '.cual-install').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        releases = prefix / 'releases'
        releases.mkdir(exist_ok=True)
        release = releases / ('0.1.0-' + uuid.uuid4().hex[:12])
        release.mkdir(mode=0o755)
        try:
            # Use disk beside the release; /tmp may be a small tmpfs in a VM.
            with tempfile.TemporaryDirectory(prefix='.build-', dir=prefix) as temporary:
                for name in ('bin', 'cual', 'skills', 'scripts'):
                    shutil.copytree(SOURCE / name, release / name, ignore=shutil.ignore_patterns('__pycache__', 'node_modules'))
                provision(release, SOURCE, Path(temporary), arch, package)
                provision_agents(release, SOURCE / 'scripts/agent-tools')
                for binary in (release / 'bin').iterdir():
                    binary.chmod(0o755)
                subprocess.run([str(release / 'bin/cual'), '--version'], check=True, timeout=20)
                subprocess.run([str(release / 'runtime/bin/node_repl'), '--help'], check=True, timeout=20, stdout=subprocess.DEVNULL)
                env = dict(os.environ, NODE_REPL_DISABLE_ANALYTICS='1')
                subprocess.run([str(release / 'runtime/bin/node'), '--input-type=module', '-e',
                                'const s = await import(process.argv[1]); const r = await s.handleRpc({type:"setup"}); if(r.target!=="linux") throw Error("Wrong platform");',
                                (release / 'runtime/lib/node_modules/@oai/sky/index.js').as_uri()], env=env, check=True, timeout=20)
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
    parser.add_argument('--package', type=Path, help='Offline official .deb matching runtime.lock.json')
    args = parser.parse_args(argv)
    if args.list_agents:
        setup.main(['--list-agents'])
        return
    if sys.version_info < (3, 12):
        raise ValueError('Python 3.12 or later is required')
    if platform.system() != 'Linux':
        raise ValueError('Install Cual inside the Linux desktop machine')
    if legacy and not args.agent and not args.export:
        args.runtime_only = True
    account, names = setup.validate(args)
    prefix = checked_prefix(args.prefix)
    if args.runtime_only:
        if args.agent or args.export or args.project or args.scope != 'user' or args.check_desktop or args.session != 'discover':
            raise ValueError('--runtime-only cannot include agent setup options')
    elif not names and not args.export and (args.yes or not sys.stdin.isatty()):
        raise ValueError('Select --agent NAME, --agent all, --agent auto, --export PATH, or --runtime-only')
    if not args.runtime_only:
        setup.installer_environment(Path(account.pw_dir), names, {} if os.getuid() == 0 and account.pw_uid else os.environ)
    if args.package and not args.package.is_file():
        raise ValueError('--package must name an existing official .deb')
    if not args.skip_system:
        if os.getuid() != 0 or not shutil.which('apt-get'):
            raise ValueError('Automatic system provisioning requires root and apt-get; otherwise provision dependencies and use --skip-system')
        subprocess.run(['apt-get', 'update'], check=True)
        subprocess.run(['apt-get', 'install', '-y', 'ca-certificates', 'python3', 'dpkg', 'libx11-6', 'libxtst6',
                        'libxi6', 'libxrandr2', 'libxfixes3', 'libxcomposite1', 'libxdamage1', 'at-spi2-core',
                        'dbus-x11', 'x11-utils'], check=True)
    install(prefix, args.package)
    print(f'Cual installed: {prefix}/current/bin/cual')
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
        subprocess.run([str(prefix / 'current/bin/cual'), 'setup', *forwarded], check=True)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        sys.exit(f'Cual installer: {exc}')
