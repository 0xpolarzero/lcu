"""Trace every internal ASAR entry without extracting or executing application code.

Packed files are hashed directly in bounded chunks. Unpacked file identities are
checked against the separately verified complete application inventory. Package
interfaces include packed manifests and hash-verified unpacked manifests.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import struct

ROOT = Path(__file__).resolve().parents[1]
CHUNK = 1024 * 1024
PACKAGE_FIELDS = ('name', 'version', 'type', 'main', 'module', 'browser', 'exports',
                  'imports', 'types', 'typings', 'bin', 'dependencies',
                  'optionalDependencies', 'peerDependencies', 'devDependencies')


def file_digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def region(stream, offset, size, *, collect=False):
    stream.seek(offset)
    remaining, digest, parts = size, hashlib.sha256(), []
    while remaining:
        block = stream.read(min(CHUNK, remaining))
        if not block:
            raise ValueError('Truncated ASAR file content')
        digest.update(block)
        if collect:
            parts.append(block)
        remaining -= len(block)
    return digest.hexdigest(), b''.join(parts) if collect else None


def safe_path(name):
    parts = PurePosixPath(name).parts
    if not name or name.startswith('/') or '\\' in name or any(p in ('.', '..') for p in parts):
        raise ValueError(f'Invalid internal ASAR path: {name}')
    return name


def entries(tree, prefix=''):
    children = tree.get('files')
    if not isinstance(children, dict):
        raise ValueError('ASAR directory is missing its files map')
    for name, entry in sorted(children.items()):
        if not isinstance(name, str) or '/' in name or name in ('.', '..'):
            raise ValueError('Invalid ASAR entry name')
        path = safe_path(prefix + name)
        if not isinstance(entry, dict):
            raise ValueError(f'Invalid ASAR entry: {path}')
        yield path, entry
        if 'files' in entry:
            yield from entries(entry, path + '/')


def capture_asar(asar, arch, root=ROOT, *, package_reference=None):
    asar, root = Path(asar), Path(root)
    application = json.loads((root / f'scripts/application-inventory.{arch}.json').read_text())
    pinned = application['files']['resources/app.asar']
    archive_size, archive_hash = asar.stat().st_size, file_digest(asar)
    if archive_size != pinned['size'] or archive_hash != pinned['sha256']:
        raise ValueError(f'ASAR differs from complete application inventory ({arch})')
    unpacked = Path(package_reference) if package_reference else Path(str(asar) + '.unpacked')
    files, packages = {}, {}
    with asar.open('rb') as stream:
        preamble = stream.read(16)
        if len(preamble) != 16:
            raise ValueError('Truncated ASAR header')
        size_payload, header_size, header_payload, json_size = struct.unpack('<4I', preamble)
        data_offset = 8 + header_size
        if (size_payload != 4 or header_payload != header_size - 4 or
                json_size > header_payload - 4 or data_offset > archive_size or
                json_size > 64 * CHUNK):
            raise ValueError('Invalid ASAR header bounds')
        header = json.loads(stream.read(json_size))
        for name, node in entries(header):
            metadata = {key: value for key, value in node.items() if key != 'files'}
            if 'files' in node:
                files[name] = {'kind': 'directory', 'header': metadata}
                continue
            if 'link' in node:
                safe_path(node['link'])
                files[name] = {'kind': 'symlink', 'target': node['link'], 'header': metadata}
                continue
            size = node.get('size')
            if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                raise ValueError(f'Invalid ASAR entry size: {name}')
            is_package = PurePosixPath(name).name == 'package.json'
            content = None
            is_unpacked = node.get('unpacked', False)
            if not isinstance(is_unpacked, bool):
                raise ValueError(f'Invalid ASAR unpacked flag: {name}')
            if is_unpacked:
                external = 'resources/app.asar.unpacked/' + name
                original = application['files'].get(external, {})
                if original.get('kind') != 'file' or original.get('size') != size:
                    raise ValueError(f'Unpacked ASAR entry is not in application inventory: {name}')
                digest = original['sha256']
                if is_package:
                    content = (unpacked / name).read_bytes()
                    if len(content) != size or hashlib.sha256(content).hexdigest() != digest:
                        raise ValueError(f'Unpacked package manifest differs from pinned bytes: {name}')
            else:
                try:
                    offset = int(node['offset'])
                except (KeyError, ValueError, TypeError):
                    raise ValueError(f'Invalid ASAR content offset: {name}') from None
                if offset < 0 or data_offset + offset + size > archive_size:
                    raise ValueError(f'ASAR content is outside archive: {name}')
                digest, content = region(stream, data_offset + offset, size, collect=is_package)
            integrity = node.get('integrity', {})
            if integrity and (integrity.get('algorithm') != 'SHA256' or integrity.get('hash') != digest):
                raise ValueError(f'ASAR content integrity mismatch: {name}')
            files[name] = {'kind': 'file', 'size': size, 'sha256': digest,
                           'unpacked': is_unpacked, 'header': metadata}
            if is_unpacked:
                files[name]['application_source'] = external
            if is_package:
                package = json.loads(content)
                packages[name] = {field: package[field] for field in PACKAGE_FIELDS if field in package}
    return {'format': 1, 'architecture': arch, 'package_version': application['package_version'],
            'official_package_sha256': application['official_package_sha256'],
            'archive': {'source': 'usr/lib/chatgpt/resources/app.asar',
                        'size': archive_size, 'sha256': archive_hash, 'data_offset': data_offset},
            'exclusions': [], 'files': files,
            'surface': {'package_interfaces': packages,
                        'application_source_modules': [name for name, entry in files.items()
                            if entry['kind'] == 'file' and name.startswith(('.vite/build/', 'webview/'))
                            and name.endswith(('.js', '.mjs', '.cjs', '.css', '.html'))]}}


def verify_asar(asar, arch, root=ROOT):
    expected = json.loads((Path(root) / f'scripts/asar-inventory.{arch}.json').read_text())
    actual = capture_asar(asar, arch, root)
    if expected != actual:
        before, after = expected['files'], actual['files']
        missing, added = sorted(before.keys() - after.keys()), sorted(after.keys() - before.keys())
        changed = sorted(name for name in before.keys() & after.keys() if before[name] != after[name])
        raise ValueError(f'ASAR inventory mismatch ({arch}): missing={missing[:8]}, added={added[:8]}, changed={changed[:8]}')
    return expected


def verify_shared_sources(root=ROOT):
    """Require all core, preload, renderer and webview source modules to match."""
    inventories = [json.loads((Path(root) / f'scripts/asar-inventory.{arch}.json').read_text())
                   for arch in ('arm64', 'x64')]
    sources = [{name: {'size': item['files'][name]['size'], 'sha256': item['files'][name]['sha256']}
                for name in item['surface']['application_source_modules']} for item in inventories]
    if sources[0] != sources[1]:
        raise ValueError('Original core/preload/renderer source differs between architectures')
    required = ('.vite/build/browser-page-preload.js', '.vite/build/preload.js')
    if not all(name in sources[0] for name in required) or not any(name.startswith('webview/') for name in sources[0]):
        raise ValueError('Original browser preload/renderer source inventory is incomplete')
    return len(sources[0])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asar', type=Path)
    parser.add_argument('--arch', choices=('arm64', 'x64'))
    parser.add_argument('--write', action='store_true', help='Record a reviewed pinned source, never used by release builds')
    parser.add_argument('--package-reference', type=Path, help='Hash-checked source of unpacked package manifests during inventory capture')
    parser.add_argument('--compare-architectures', action='store_true')
    args = parser.parse_args()
    if args.compare_architectures:
        print(f'PASS: {verify_shared_sources()} original core/preload/renderer source modules match both architectures')
    else:
        if args.asar is None or args.arch is None:
            parser.error('--asar and --arch are required')
        if args.write:
            inventory = capture_asar(args.asar, args.arch, package_reference=args.package_reference)
            (ROOT / f'scripts/asar-inventory.{args.arch}.json').write_text(json.dumps(inventory, indent=2) + '\n')
        else:
            inventory = verify_asar(args.asar, args.arch)
        leaves = sum(entry['kind'] != 'directory' for entry in inventory['files'].values())
        print(f'PASS: {leaves} ASAR leaves, {len(inventory["surface"]["package_interfaces"])} package interfaces; {args.arch}')
