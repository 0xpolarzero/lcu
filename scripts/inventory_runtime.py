"""Inventory and verify every byte of the original architecture-specific runtime.

The official package checksum is verified by the build before this check. No
runtime file is excluded. The additional surface indexes make public exports,
declarations, configuration, and dynamically selected guidance reviewable.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
MODULES = 'lib/node_modules/'
OAI = MODULES + '@oai/'
HOST_SOURCES = {
    'bin/codex': 'codex',
    'bin/codex-code-mode-host': 'codex-code-mode-host',
    'plugins/browser': 'plugins/openai-bundled/plugins/browser',
    'plugins/chrome': 'plugins/openai-bundled/plugins/chrome',
    'plugins/unified-computer-use': 'plugins/openai-bundled/plugins/unified-computer-use',
}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def category(path):
    """Describe retained files; categories never determine whether to copy them."""
    if path == 'manifest.json':
        return 'runtime-manifest'
    if '/plugin/' in path:
        return 'upstream-host-plugin'
    if path.endswith('/package.json'):
        return 'package-metadata'
    if path.startswith(OAI) and any(part in path for part in
            ('/instructions/', '/docs/', '/environment-docs/', '/skill/references/')):
        return 'instruction-resource'
    if path.startswith(OAI) and path.endswith('.d.ts'):
        return 'upstream-api-declaration'
    if path.startswith('bin/') or path.startswith(OAI) and '/bin/' in path:
        return 'executable'
    if path.startswith(OAI):
        return 'upstream-runtime'
    return 'bundled-dependency'


def inventory(runtime):
    runtime = Path(runtime)
    result = {}
    # Do not follow symlinks: their targets are separately hashed if internal.
    for directory, directories, files in os.walk(runtime, followlinks=False):
        for name in sorted(directories + files):
            path = Path(directory, name)
            relative = path.relative_to(runtime).as_posix()
            info = path.lstat()
            entry = {'mode': stat.S_IMODE(info.st_mode)}
            if stat.S_ISLNK(info.st_mode):
                entry.update(kind='symlink', target=os.readlink(path))
            elif stat.S_ISREG(info.st_mode):
                entry.update(kind='file', size=info.st_size, sha256=digest(path),
                             category=category(relative))
            elif stat.S_ISDIR(info.st_mode):
                entry.update(kind='directory')
            else:
                raise ValueError(f'Unexpected runtime file type: {relative}')
            result[relative] = entry
    return dict(sorted(result.items()))


def surface(runtime, files, primary_prefixes=(OAI,)):
    """Index source declarations and complete document capability graphs."""
    runtime = Path(runtime)
    packages, declarations, documents, plugins = {}, [], {}, []
    environment = {}
    for name, entry in files.items():
        if entry['kind'] != 'file':
            continue
        path = runtime / name
        if name.endswith('/package.json'):
            package = json.loads(path.read_text())
            packages[name] = {key: package[key] for key in
                             ('name', 'version', 'type', 'main', 'exports', 'imports',
                              'types', 'bin', 'dependencies', 'optionalDependencies')
                             if key in package}
        if not name.startswith(primary_prefixes):
            continue
        if name.endswith('.d.ts'):
            declarations.append(name)
        if '/plugin/' in name:
            plugins.append(name)
        if name.endswith('/documents.json'):
            graph = json.loads(path.read_text())
            # Each declared named resource must exist, including conditional docs.
            for item in graph:
                target = path.parent / (item['name'] + '.md')
                if not target.is_file():
                    raise ValueError(f'Document graph points to missing resource: {target}')
            documents[name] = graph
        if name.endswith(('.js', '.mjs', '.cjs', '.ts', '.json', '.md')):
            text = path.read_text(errors='replace')
            names = sorted(set(re.findall(
                r'\b(?:CUA_REPL|NODE_REPL|TINYSKY_ALT|OAI|SKY|CODEX|'
                r'OPENAI|BROWSER|PLAYWRIGHT)_[A-Z][A-Z0-9_]*\b', text)))
            if names:
                environment[name] = names
    return {'package_interfaces': packages,
            'api_declarations': declarations,
            'dynamic_document_graphs': documents,
            'upstream_plugin_files': plugins,
            'configuration_identifiers': environment}


def capture(runtime, arch, root=ROOT):
    runtime, root = Path(runtime), Path(root)
    package = json.loads((root / 'runtime.lock.json').read_text())
    manifest = json.loads((runtime / 'manifest.json').read_text())
    if (manifest['platform'], manifest['arch'], manifest['runtime_archive_version']) != (
            'linux', arch, package['runtime']):
        raise ValueError('Unexpected runtime identity')
    files = inventory(runtime)
    return {'format': 1, 'architecture': arch,
            'package_version': package['version'],
            'official_package_sha256': package['architectures'][arch]['sha256'],
            'runtime_manifest': manifest, 'exclusions': [],
            'files': files, 'surface': surface(runtime, files)}


def verify(runtime, arch, root=ROOT):
    """Reject missing, additional, modified, renamed, or permission-changed files."""
    root = Path(root)
    expected = json.loads((root / f'scripts/runtime-inventory.{arch}.json').read_text())
    actual = capture(runtime, arch, root)
    if expected != actual:
        before, after = expected['files'], actual['files']
        missing = sorted(before.keys() - after.keys())
        added = sorted(after.keys() - before.keys())
        changed = sorted(path for path in before.keys() & after.keys()
                         if before[path] != after[path])
        detail = (f'missing={missing[:8]}, added={added[:8]}, changed={changed[:8]}'
                  if missing or added or changed else 'metadata/surface mismatch')
        raise ValueError(f'Runtime inventory mismatch ({arch}): {detail}')
    return expected


def compare(source, destination):
    """Check the copied runtime has exactly the same complete file inventory."""
    if inventory(source) != inventory(destination):
        raise ValueError('Runtime copy differs from the original; no exclusions are allowed')


def capture_host(resources, arch, root=ROOT):
    """Inventory complete original plugins and companion executables outside cua_node."""
    resources, root = Path(resources), Path(root)
    package = json.loads((root / 'runtime.lock.json').read_text())
    files, sources = {}, {}
    for target, source in HOST_SOURCES.items():
        path = resources / source
        if path.is_dir():
            for relative, entry in inventory(path).items():
                files[f'{target}/{relative}'] = entry
                sources[f'{target}/{relative}'] = f'{source}/{relative}'
        elif path.is_file():
            info = path.stat()
            files[target] = {'kind': 'file', 'mode': stat.S_IMODE(info.st_mode),
                             'size': info.st_size, 'sha256': digest(path),
                             'category': 'companion-executable'}
            sources[target] = source
        else:
            raise ValueError(f'Missing host integration: {path}')
    source_files = {sources[target]: entry for target, entry in files.items()}
    return {'format': 1, 'architecture': arch, 'package_version': package['version'],
            'official_package_sha256': package['architectures'][arch]['sha256'],
            'source_mapping': HOST_SOURCES, 'files': dict(sorted(files.items())),
            'surface': surface(resources, source_files,
                               primary_prefixes=('plugins/openai-bundled/plugins/',))}


def verify_host(resources, arch, root=ROOT):
    expected = json.loads((Path(root) / f'scripts/host-inventory.{arch}.json').read_text())
    if capture_host(resources, arch, root) != expected:
        raise ValueError(f'Host integration inventory differs from pinned source ({arch})')
    return expected


def verify_host_copy(destination, arch, root=ROOT):
    """Verify copied upstream host entries; LCU integration files may be added separately."""
    expected = json.loads((Path(root) / f'scripts/host-inventory.{arch}.json').read_text())['files']
    destination = Path(destination)
    actual = {}
    # A retained full application can expose the original paths through aliases.
    # Follow only these known roots, then hash their complete original contents.
    for target, source in HOST_SOURCES.items():
        path = destination / target
        if path.is_symlink() and os.readlink(path) != '../application/resources/' + source:
            raise ValueError(f'Unexpected upstream host alias: {target}')
        if path.is_dir():
            actual.update({f'{target}/{relative}': entry for relative, entry in inventory(path).items()})
        elif path.is_file():
            actual[target] = {'kind': 'file', 'mode': stat.S_IMODE(path.stat().st_mode),
                              'size': path.stat().st_size, 'sha256': digest(path)}
    for path, entry in expected.items():
        found = actual.get(path)
        # Classification depends on the root; it does not alter runtime bytes.
        if found is None or {k: v for k, v in found.items() if k != 'category'} != {
                k: v for k, v in entry.items() if k != 'category'}:
            raise ValueError(f'Copied host integration differs: {path}')


def capture_application_package(deb, arch, root=ROOT):
    """Hash the complete application directly from the verified .deb tar stream."""
    lock = json.loads((Path(root) / 'runtime.lock.json').read_text())
    if digest(Path(deb)) != lock['architectures'][arch]['sha256']:
        raise ValueError('Official application package checksum mismatch')
    prefix = 'usr/lib/chatgpt/'
    files, hardlinks = {}, {}
    root_mode = None
    # These pinned packages contain data.tar.xz. ar permits a read-only audit on
    # macOS; packaging on Linux uses its native Debian reader.
    command = (['dpkg-deb', '--fsys-tarfile', str(deb)] if shutil.which('dpkg-deb')
               else ['ar', '-p', str(deb), 'data.tar.xz'])
    process = subprocess.Popen(command, stdout=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=process.stdout, mode='r|*') as archive:
            for member in archive:
                name = member.name.removeprefix('./').rstrip('/')
                if name == prefix.rstrip('/'):
                    root_mode = member.mode
                    continue
                if not name.startswith(prefix):
                    continue
                relative = name[len(prefix):]
                if not relative or '..' in Path(relative).parts:
                    raise ValueError('Invalid application archive path')
                entry = {'mode': member.mode}
                if member.isdir():
                    entry.update(kind='directory')
                elif member.issym():
                    entry.update(kind='symlink', target=member.linkname)
                elif member.isfile():
                    stream = archive.extractfile(member)
                    entry.update(kind='file', size=member.size,
                                 sha256=hashlib.file_digest(stream, 'sha256').hexdigest(),
                                 category=category(relative))
                elif member.islnk():
                    link = member.linkname.removeprefix('./')
                    if not link.startswith(prefix):
                        raise ValueError('Application hardlink escapes inventory root')
                    hardlinks[relative] = link[len(prefix):]
                    continue
                else:
                    raise ValueError(f'Unexpected application archive type: {relative}')
                if relative in files:
                    raise ValueError(f'Duplicate application archive entry: {relative}')
                files[relative] = entry
        if process.wait() != 0:
            raise ValueError('Unable to read official application archive')
    finally:
        process.stdout.close()
        if process.poll() is None:
            process.terminate()
            process.wait()
    for name, target in hardlinks.items():
        if target not in files or files[target]['kind'] != 'file':
            raise ValueError(f'Unresolved application hardlink: {name}')
        files[name] = {**files[target], 'category': category(name)}
    if root_mode is None or not files:
        raise ValueError('Official package has no application tree')
    return {'format': 1, 'architecture': arch, 'package_version': lock['version'],
            'official_package_sha256': lock['architectures'][arch]['sha256'],
            'source_root': 'usr/lib/chatgpt', 'root_mode': root_mode, 'exclusions': [],
            'files': dict(sorted(files.items()))}


def verify_application(application, arch, root=ROOT):
    """Verify every application file, including app.asar and the native Owl shell."""
    expected = json.loads((Path(root) / f'scripts/application-inventory.{arch}.json').read_text())
    actual = inventory(application)
    if actual != expected['files'] or stat.S_IMODE(Path(application).stat().st_mode) != expected['root_mode']:
        before = expected['files']
        missing = sorted(before.keys() - actual.keys())
        added = sorted(actual.keys() - before.keys())
        changed = sorted(name for name in before.keys() & actual.keys() if before[name] != actual[name])
        raise ValueError(f'Application inventory mismatch ({arch}): missing={missing[:8]}, added={added[:8]}, changed={changed[:8]}')
    return expected


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--arch', choices=('arm64', 'x64'), required=True)
    parser.add_argument('--write', action='store_true',
                        help='Record a separately verified official extraction for review')
    parser.add_argument('--host-resources', type=Path,
                        help='Also inventory companion executables and complete original plugins')
    args = parser.parse_args()
    if args.write:
        target = ROOT / f'scripts/runtime-inventory.{args.arch}.json'
        target.write_text(json.dumps(capture(args.runtime, args.arch), indent=2) + '\n')
    result = verify(args.runtime, args.arch)
    count = sum(item['kind'] != 'directory' for item in result['files'].values())
    print(f'Complete {args.arch} runtime verified: {count} files/links, zero exclusions.')
    if args.host_resources:
        if args.write:
            target = ROOT / f'scripts/host-inventory.{args.arch}.json'
            target.write_text(json.dumps(capture_host(args.host_resources, args.arch), indent=2) + '\n')
        host = verify_host(args.host_resources, args.arch)
        count = sum(item['kind'] != 'directory' for item in host['files'].values())
        print(f'Original {args.arch} host integrations verified: {count} files/links.')
