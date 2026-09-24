#!/usr/bin/env python3
"""Stable account-local launcher for the selected thin Windows release."""

import json
from pathlib import Path
import subprocess
import sys


def selected_release(prefix):
    prefix = Path(prefix).resolve(strict=True)
    descriptor = json.loads((prefix / 'current.json').read_text())
    name = descriptor.get('release')
    if (not isinstance(name, str) or not name or '/' in name or '\\' in name or
            name in ('.', '..') or any(ord(character) < 32 for character in name)):
        raise ValueError('Invalid selected Windows release name.')
    release = prefix / 'releases' / name
    if release.is_symlink() or release.resolve(strict=True).parent != (prefix / 'releases').resolve(strict=True):
        raise ValueError('Selected Windows release leaves the managed prefix.')
    if not (release / 'bin/lcu').is_file():
        raise ValueError('Selected Windows release is incomplete.')
    return release


def main(argv=None):
    prefix = Path(__file__).resolve().parent
    release = selected_release(prefix)
    return subprocess.call([sys.executable, '-B', str(release / 'bin/lcu'), *(sys.argv[1:] if argv is None else argv)])


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f'LCU Windows launcher: {exc}')
