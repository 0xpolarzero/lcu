"""`lcu prune`: drop superseded release and app generations to reclaim space.

Each install publishes a new `<prefix>/releases/<name>`. Windows also keeps a
private app generation under `<prefix>/apps/`; LCU 0.7.0 and earlier did the
same on Linux, which now uses the installed app in place. Nothing removes old
generations automatically. Pruning keeps the current release plus the most
recent others and every app generation a kept release still references, so
it also reclaims Linux app copies left by earlier versions. It refuses to
touch anything that does not match the layout the installers create.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil

# Release dirs are `<version>-<uuid[:12]>`; Linux app generations are
# `<version>-<arch>-<digest[:16]>`; Windows app generations are a bare sha256.
_RELEASE = re.compile(r'.+-[0-9a-f]{12}$')
_LINUX_APP = re.compile(r'.+-(?:arm64|x64)-[0-9a-f]{16}$')
_WINDOWS_APP = re.compile(r'[0-9a-f]{64}$')


def _human(size):
    value = float(size)
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if value < 1024 or unit == 'TiB':
            return f'{value:.0f} {unit}' if unit == 'B' else f'{value:.1f} {unit}'
        value /= 1024


def _tree_size(path):
    total = path.lstat().st_size
    for parent, directories, files in os.walk(path, followlinks=False):
        for name in directories + files:
            try:
                total += (Path(parent) / name).lstat().st_size
            except OSError:
                pass
    return total


def _release_current(prefix, releases, windows):
    """Resolve the current release pointer and confirm it lands in releases."""
    if windows:
        pointer = prefix / 'current.json'
        if pointer.is_symlink() or not pointer.is_file():
            raise ValueError(f'Not an LCU installation: missing {pointer}')
        name = json.loads(pointer.read_text()).get('release')
        if not isinstance(name, str) or '/' in name or '\\' in name or name in ('', '.', '..'):
            raise ValueError('Invalid current.json release pointer.')
        current = releases / name
        if current.is_symlink() or not current.is_dir():
            raise ValueError('current.json does not point at a release directory.')
        return current
    pointer = prefix / 'current'
    if not pointer.is_symlink():
        raise ValueError(f'Not an LCU installation: {pointer} is not a symlink')
    current = pointer.resolve()
    if current.parent != releases.resolve() or not current.is_dir():
        raise ValueError('current does not resolve into <prefix>/releases.')
    return current


def _entries(directory, pattern):
    """Return matching child directories, refusing unexpected non-dot entries."""
    found = []
    for child in sorted(directory.iterdir()):
        if child.name.startswith('.'):
            continue  # Transient install staging (.app-stage-*, .<hex>).
        if child.is_symlink() or not child.is_dir() or not pattern.fullmatch(child.name):
            raise ValueError(f'Refusing to prune: unexpected entry {child}')
        found.append(child)
    return found


def _generation_dir(release, apps, windows):
    descriptor = json.loads((release / 'installation.json').read_text())
    if descriptor.get('platform', 'linux') == 'darwin':
        return None
    app = descriptor.get('app')
    if not isinstance(app, str) or not app:
        raise ValueError(f'Release {release.name} has no app descriptor.')
    if not windows and Path(app).is_absolute() and 'sha256' not in descriptor:
        return None  # Linux release using the installed app in place.
    resolved = (Path(app) if windows else (release / app)).resolve()
    apps = apps.resolve()
    for candidate in (resolved, *resolved.parents):
        if candidate.parent == apps:
            return candidate
    raise ValueError(f'Release {release.name} references an app outside {apps}.')


def main(root, argv):
    parser = argparse.ArgumentParser(prog='lcu prune',
                                     description='Remove superseded LCU release and app generations.')
    parser.add_argument('--keep', type=int, default=2,
                        help='Number of releases to keep, including current (minimum 1).')
    parser.add_argument('--yes', action='store_true', help='Delete instead of a dry run.')
    args = parser.parse_args(argv)
    keep = max(args.keep, 1)

    root = Path(root).resolve()
    if root.parent.name != 'releases':
        raise ValueError('lcu prune must run from an installed <prefix>/releases/<name> release.')
    prefix = root.parent.parent
    releases = prefix / 'releases'
    windows = json.loads((root / 'installation.json').read_text()).get('platform') == 'windows'
    if (prefix / '.lcu-install').is_symlink() or not (prefix / '.lcu-install').is_file():
        raise ValueError(f'Not an LCU installation: missing {prefix / ".lcu-install"}')
    if releases.is_symlink() or not releases.is_dir():
        raise ValueError(f'Not an LCU installation: {releases} is missing or a symlink')

    lock = None
    if not windows:
        import fcntl
        lock = (prefix / '.lcu-install').open('a')
        fcntl.flock(lock, fcntl.LOCK_EX)
    else:
        # install_windows.py uses atomic replaces, not a lock file; nothing to take.
        pass
    try:
        current = _release_current(prefix, releases, windows)
        all_releases = _entries(releases, _RELEASE)
        others = sorted((r for r in all_releases if r != current and r != root),
                        key=lambda r: r.stat().st_mtime, reverse=True)
        kept = {current, root, *others[:max(keep - 1, 0)]}
        remove_releases = [r for r in all_releases if r not in kept]

        apps = prefix / 'apps'
        remove_apps = []
        if apps.exists():
            if apps.is_symlink() or not apps.is_dir():
                raise ValueError(f'Refusing to prune: {apps} is not a directory')
            pattern = _WINDOWS_APP if windows else _LINUX_APP
            all_apps = _entries(apps, pattern)
            referenced = {_generation_dir(r, apps, windows) for r in kept}
            referenced.discard(None)
            remove_apps = [a for a in all_apps if a not in referenced]

        removals = remove_releases + remove_apps
        if not removals:
            print('Nothing to prune; current and recent generations are already the only ones.')
            return
        # Guard: only ever delete real directories directly under releases/apps.
        for path in removals:
            if path.is_symlink() or not path.is_dir() or path.parent not in (releases, apps):
                raise ValueError(f'Refusing to remove unexpected path: {path}')

        total = 0
        for path in removals:
            size = _tree_size(path)
            total += size
            action = 'Removed' if args.yes else 'Would remove'
            if args.yes:
                shutil.rmtree(path)
            print(f'{action} {path} ({_human(size)})')
        print(f'Total: {_human(total)} across {len(removals)} generation(s).')
        if not args.yes:
            print('Rerun with --yes to delete. '
                  'Restart or stop agents using older LCU releases first.')
    finally:
        if lock is not None:
            lock.close()
