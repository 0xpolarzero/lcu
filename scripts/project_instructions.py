"""Verify complete upstream instruction sets and byte-identical local references.

The runtime is copied unchanged. This module verifies its guidance and the copies
provided beside LCU's skill, including inactive modes and dynamic browser guides.
Standalone integration notes belong in SKILL.md, never in rewritten upstream text.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def project_text(data, entry):
    if digest(data) != entry['sha256']:
        raise ValueError(f'Upstream instruction changed: {entry["source"]}')
    if entry['edits']:
        raise ValueError(f'Instruction edits are not allowed: {entry["source"]}')
    if digest(data) != entry['output_sha256']:
        raise ValueError(f'Instruction output differs from upstream: {entry["source"]}')
    return data


def entries(root=ROOT):
    manifest = json.loads((root / 'scripts/instructions.lock.json').read_text())
    if manifest['format'] != 2:
        raise ValueError('Unsupported instruction projection format')
    return manifest['files']


def verify_outputs(root=ROOT, files=None):
    for entry in entries(root) if files is None else files:
        for target in entry['targets']:
            path = root / target
            if not path.is_file() or digest(path.read_bytes()) != entry['output_sha256']:
                raise ValueError(f'Instruction drift: {target}; regenerate from pinned upstream text')


def project(upstream_modules, root=ROOT, *, write=False):
    upstream_modules, root = Path(upstream_modules), Path(root)
    manifest = json.loads((root / 'scripts/instructions.lock.json').read_text())
    files = entries(root)
    scopes = {'modules': upstream_modules, 'resources': upstream_modules.parents[2]}
    expected_sources = {(entry.get('scope', 'modules'), entry['source']) for entry in files}
    discovered = set()
    for group in manifest['resource_roots']:
        base = scopes[group['scope']]
        source = base / group['source']
        if not source.is_dir():
            raise ValueError(f'Missing instruction resource root: {source}')
        for path in source.rglob('*'):
            if path.is_file() and (not group.get('suffixes') or path.suffix in group['suffixes']):
                discovered.add((group['scope'], path.relative_to(base).as_posix()))
    # Explicit individual sources cover package documentation and plugin skills.
    discovered.update((entry.get('scope', 'modules'), entry['source']) for entry in files
                      if entry.get('individual'))
    if discovered != expected_sources:
        raise ValueError('Instruction inventory drift: '
                         f'missing={sorted(expected_sources - discovered)}, '
                         f'unclassified={sorted(discovered - expected_sources)}')
    for entry in files:
        if entry['edits'] or entry['sha256'] != entry['output_sha256']:
            raise ValueError('Upstream instruction rewrites are forbidden; use standalone wrapper notes')
        output = project_text((scopes[entry.get('scope', 'modules')] / entry['source']).read_bytes(), entry)
        if write:
            for target in entry['targets']:
                path = root / target
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(output)
    verify_outputs(root, files)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream-modules', type=Path, help='Verified runtime lib/node_modules directory')
    parser.add_argument('--write', action='store_true', help='Regenerate reviewed files from upstream')
    args = parser.parse_args()
    if args.write and args.upstream_modules is None:
        parser.error('--write requires --upstream-modules')
    if args.upstream_modules:
        project(args.upstream_modules, write=args.write)
    else:
        verify_outputs()
    print('Instruction projection verified.')
