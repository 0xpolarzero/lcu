#!/usr/bin/env python3
"""Install thin LCU beside the current user's pinned official Windows MSIX."""

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import uuid

SOURCE = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(SOURCE))

from bundle import VERSION, architecture, verify
from lcu.windows import resolve_installed_windows_app


def checked_prefix(prefix):
    prefix = Path(prefix)
    if not prefix.is_absolute() or '..' in prefix.parts or len(prefix.parts) < 3:
        raise ValueError('Choose a dedicated absolute Windows installation directory.')
    for item in (prefix, *prefix.parents):
        if item.is_symlink():
            raise ValueError(f'Refusing a linked Windows installation path: {item}')
    prefix = prefix.resolve()
    if prefix == SOURCE.resolve() or SOURCE.resolve().is_relative_to(prefix):
        raise ValueError('Install outside the extracted release archive.')
    if prefix.exists() and any(prefix.iterdir()) and not (prefix / '.lcu-install').is_file():
        raise ValueError('Installation directory is occupied by another application.')
    return prefix


def install(prefix):
    if platform.system() != 'Windows':
        raise ValueError('The Windows installer must run in Windows 11 x64.')
    if sys.version_info < (3, 12):
        raise ValueError('Python 3.12 or later is required.')
    arch = architecture('windows')
    verify(SOURCE, arch, 'windows')
    prefix = checked_prefix(prefix)
    lock = json.loads((SOURCE / 'runtime.lock.json').read_text())['platforms']['windows']
    entry = lock['architectures']['x64']
    selected = resolve_installed_windows_app(expected_version=lock['version'],
        expected_runtime=lock['runtime'], expected_hashes=entry['components'])
    # The app stays under Windows MSIX management. No source app file is copied.
    prefix.mkdir(parents=True, exist_ok=True)
    (prefix / '.lcu-install').touch(exist_ok=True)
    releases = prefix / 'releases'
    releases.mkdir(exist_ok=True)
    release = releases / (VERSION + '-' + uuid.uuid4().hex[:12])
    try:
        shutil.copytree(SOURCE, release)
        verify(release, arch, 'windows')
        (release / 'installation.json').write_text(json.dumps({
            'platform': 'windows', 'architecture': 'x64', 'app': str(selected.app),
            'package_version': lock['version'], 'runtime': lock['runtime'],
            'sha256': entry['sha256'],
        }, indent=2) + '\n')
        from lcu.runtime import paths
        paths(release)
        stable = prefix / 'windows_launcher.py'
        shutil.copy2(release / 'scripts/windows_launcher.py', stable)
        (prefix / 'lcu.cmd').write_text('@echo off\r\npy -3.12 "%~dp0windows_launcher.py" %*\r\nexit /b %ERRORLEVEL%\r\n')
        temporary = prefix / ('.current-' + uuid.uuid4().hex + '.json')
        temporary.write_text(json.dumps({'release': release.name}) + '\n')
        os.replace(temporary, prefix / 'current.json')
    except BaseException:
        shutil.rmtree(release, ignore_errors=True)
        raise
    return release


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    default = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / 'LCU'
    parser.add_argument('--prefix', type=Path, default=default)
    parser.add_argument('--runtime-only', action='store_true')
    parser.add_argument('--agent', action='append', choices=('codex', 'claude-code', 'pi'))
    parser.add_argument('--chrome', action='store_true')
    parser.add_argument('--yes', action='store_true')
    parser.add_argument('--scope', choices=('user', 'project'), default='user')
    parser.add_argument('--project', type=Path)
    args = parser.parse_args(argv)
    if args.runtime_only and (args.agent or args.chrome or args.project or args.scope != 'user'):
        parser.error('--runtime-only cannot include agent setup options')
    if not args.runtime_only and not args.agent:
        parser.error('Choose --agent codex, --agent claude-code, or --agent pi, or --runtime-only')
    release = install(args.prefix)
    print(f'LCU installed: {args.prefix / "lcu.cmd"}')
    if not args.runtime_only:
        command = [sys.executable, '-B', str(release / 'bin/lcu'), 'setup',
                   '--prefix', str(args.prefix), '--session', 'direct', '--scope', args.scope]
        for agent in args.agent:
            command += ['--agent', agent]
        if args.project:
            command += ['--project', str(args.project)]
        if args.chrome:
            command += ['--chrome']
        if args.yes:
            command += ['--yes']
        subprocess.run(command, check=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise SystemExit(f'LCU Windows installer: {exc}')
