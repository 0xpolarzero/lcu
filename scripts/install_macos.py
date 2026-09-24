#!/usr/bin/env python3
"""Select an existing signed macOS app and install LCU's thin adapters."""
import json
from pathlib import Path
import subprocess
import sys

SOURCE = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(SOURCE))

from lcu import setup
from lcu.platforms import resolve_installed_mac_app
from bundle import architecture, verify
from install import checked_prefix, select_release


def install(prefix, application, *, account=None):
    prefix = checked_prefix(prefix)
    arch = architecture('darwin')
    verify(SOURCE, arch, 'darwin')
    lock = json.loads((SOURCE / 'runtime.lock.json').read_text())['platforms']['darwin']
    entry = lock['architectures'].get(arch)
    if entry is None:
        raise ValueError(f'No verified macOS {arch} application is pinned in this release')
    selected = resolve_installed_mac_app(application, expected_version=lock['version'],
        expected_runtime=lock['runtime'], expected_hashes=entry['components'], arch=arch)
    # Validate before creating the prefix or changing the selected release.
    prefix.mkdir(parents=True, exist_ok=True)
    (prefix / '.lcu-install').touch(exist_ok=True)
    return select_release(prefix, arch, selected.app, {
        'platform': 'darwin', 'architecture': arch, 'package_version': lock['version'],
        'runtime': lock['runtime'],
    }, account=account, target='darwin', source=SOURCE)


def main(argv=None):
    parser = setup.parser()
    parser.description = __doc__
    parser.set_defaults(prefix=Path.home() / '.local/share/lcu', session='direct')
    parser.add_argument('--existing-app', type=Path, default=Path('/Applications/ChatGPT.app'),
                        help='Pinned signed ChatGPT.app; reused in place without modification')
    parser.add_argument('--runtime-only', action='store_true')
    parser.add_argument('--offline', action='store_true', help='Accepted for consistency; macOS setup always uses local files')
    parser.add_argument('--skip-system', action='store_true', help='Accepted for consistency; no system packages are installed')
    args = parser.parse_args(argv)
    if args.list_agents:
        setup.main(['--list-agents'])
        return
    if sys.version_info < (3, 12):
        raise ValueError('Python 3.12 or later is required')
    account, names = setup.validate(args)
    if args.session != 'direct':
        raise ValueError('macOS uses --session direct; XFCE session discovery is Linux-only')
    if args.runtime_only:
        if args.agent or args.export or args.project or args.scope != 'user' or args.check_desktop or args.chrome:
            raise ValueError('--runtime-only cannot include agent setup options')
    elif not names and not args.export and (args.yes or not sys.stdin.isatty()):
        raise ValueError('Select --agent NAME, --export PATH, or --runtime-only')
    install(args.prefix, args.existing_app, account=account)
    runtime = args.prefix / 'current/bin/lcu'
    print(f'LCU installed: {runtime}')
    print('The signed application is reused in place. An app update requires matching reviewed pins.')
    if not args.runtime_only:
        forwarded = ['--prefix', str(args.prefix), '--user', account.pw_name, '--scope', args.scope,
                     '--session', 'direct']
        for name in args.agent:
            forwarded += ['--agent', name]
        for option in ('project', 'export'):
            if getattr(args, option):
                forwarded += ['--' + option, str(getattr(args, option))]
        for option in ('yes', 'check_desktop', 'chrome'):
            if getattr(args, option):
                forwarded += ['--' + option.replace('_', '-')]
        subprocess.run([str(runtime), 'setup', *forwarded], check=True)
    print('macOS Screen Recording and Accessibility approvals belong to the original Codex Computer Use helper. '
          'Grant them in System Settings when using native control; setup never grants them silently.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        sys.exit(f'LCU macOS installer: {exc}')
