"""Reproduce Linux instructions from pinned upstream text and reviewed line edits."""
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
    lines = data.decode().splitlines(keepends=True)
    result, cursor = [], 0
    for edit in entry['edits']:
        start, end = edit['start'] - 1, edit['end']
        if not cursor <= start < end <= len(lines) or not edit['reason'].strip():
            raise ValueError(f'Invalid instruction edit: {entry["source"]}: {edit}')
        result.extend(lines[cursor:start])
        result.append(edit['replacement'])
        cursor = end
    result.extend(lines[cursor:])
    output = ''.join(result).encode()
    if digest(output) != entry['output_sha256']:
        raise ValueError(f'Projected instruction differs from reviewed output: {entry["source"]}')
    return output


def entries(root=ROOT):
    manifest = json.loads((root / 'scripts/instructions.lock.json').read_text())
    if manifest['format'] != 1:
        raise ValueError('Unsupported instruction projection format')
    return manifest['files']


def verify_outputs(root=ROOT, files=None):
    for entry in entries(root) if files is None else files:
        for target in entry['targets']:
            path = root / target
            if not path.is_file() or digest(path.read_bytes()) != entry['output_sha256']:
                raise ValueError(f'Instruction drift: {target}; regenerate from pinned upstream text')


def project(upstream_modules, root=ROOT, *, write=False):
    files = entries(root)
    for entry in files:
        output = project_text((upstream_modules / entry['source']).read_bytes(), entry)
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
