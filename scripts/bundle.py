"""Local release inventory. This module has no download or build dependencies."""
import hashlib
import json
import os
from pathlib import Path
import platform

VERSION = '0.2.0'


def architecture():
    arch = {'aarch64': 'arm64', 'arm64': 'arm64', 'x86_64': 'x64', 'amd64': 'x64'}.get(platform.machine())
    if platform.system() != 'Linux' or arch is None:
        raise ValueError('LCU requires Linux ARM64 or x86-64.')
    return arch


def inventory(root):
    root = root.resolve()
    files = {}
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root).as_posix()
        if relative == 'bundle.json':
            continue
        if path.is_symlink():
            target = os.readlink(path)
            if Path(target).is_absolute() or not path.resolve().is_relative_to(root):
                raise ValueError(f'Unsafe bundle symlink: {relative}')
            files[relative] = {'type': 'symlink', 'target': target}
        elif path.is_file():
            with path.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            files[relative] = {'type': 'file', 'sha256': digest, 'mode': path.stat().st_mode & 0o777}
        elif not path.is_dir():
            raise ValueError(f'Unsupported bundle entry: {relative}')
    return files


def seal(root, arch):
    manifest = {'format': 1, 'version': VERSION, 'platform': 'linux', 'architecture': arch,
                'files': inventory(root)}
    (root / 'bundle.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')


def verify(root, arch):
    path = root / 'bundle.json'
    if not path.is_file() or path.is_symlink():
        raise ValueError('Install from an extracted LCU release bundle. Source checkouts contain no runtime; build a release with scripts/build_bundle.py first.')
    manifest = json.loads(path.read_text())
    if not isinstance(manifest, dict) or manifest.get('format') != 1 or manifest.get('platform') != 'linux' or manifest.get('version') != VERSION:
        raise ValueError('Unsupported LCU bundle manifest')
    if manifest.get('architecture') != arch:
        raise ValueError(f'Bundle architecture {manifest.get("architecture")} does not match this machine ({arch})')
    expected, actual = manifest.get('files'), inventory(root)
    if not isinstance(expected, dict) or expected != actual:
        raise ValueError('LCU bundle integrity check failed; extract a clean release archive.')
    return manifest
