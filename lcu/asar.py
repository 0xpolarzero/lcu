"""Small bounded reader for selected Electron ASAR members."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import struct
from typing import Iterable


MAX_HEADER_SIZE = 64 * 1024 * 1024
MAX_MEMBER_SIZE = 64 * 1024 * 1024


def _read_header(archive: Path):
    archive = Path(archive)
    size = archive.stat().st_size
    with archive.open('rb') as stream:
        preamble = stream.read(16)
        if len(preamble) != 16:
            raise ValueError('ASAR header is truncated.')
        size_payload, header_size, header_payload, json_size = struct.unpack('<4I', preamble)
        data_offset = 8 + header_size
        if (size_payload != 4 or header_size < 8 or header_payload != header_size - 4 or
                json_size > header_payload - 4 or json_size > MAX_HEADER_SIZE or
                data_offset > size):
            raise ValueError('ASAR header is invalid.')
        encoded = stream.read(json_size)
        if len(encoded) != json_size:
            raise ValueError('ASAR header JSON is truncated.')
    try:
        header = json.loads(encoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError('ASAR header JSON is invalid.') from exc
    if not isinstance(header, dict) or not isinstance(header.get('files'), dict):
        raise ValueError('ASAR header has no file tree.')
    return archive, header, data_offset, size


def _valid_path(name: str) -> tuple[str, ...]:
    if (not isinstance(name, str) or not name or '\\' in name or '\x00' in name or
            name.startswith('/')):
        raise ValueError(f'Invalid ASAR member path: {name!r}')
    path = PurePosixPath(name)
    if any(part in ('', '.', '..') for part in path.parts):
        raise ValueError(f'Invalid ASAR member path: {name!r}')
    return path.parts


def _member_node(header: dict, name: str) -> dict:
    node = header
    try:
        for part in _valid_path(name):
            node = node['files'][part]
    except (KeyError, TypeError) as exc:
        raise ValueError(f'ASAR member is missing: {name}') from exc
    if not isinstance(node, dict):
        raise ValueError(f'ASAR member entry is invalid: {name}')
    return node


def list_asar_members(archive: Path) -> tuple[str, ...]:
    """List member paths from the bounded ASAR header without reading payloads."""
    _, header, _, _ = _read_header(archive)
    result = []

    def visit(directory: dict, prefix: str = ''):
        entries = directory.get('files')
        if not isinstance(entries, dict):
            raise ValueError('ASAR directory entry is invalid.')
        for name, node in entries.items():
            if (not isinstance(name, str) or not name or '/' in name or '\\' in name or
                    name in ('.', '..') or '\x00' in name or not isinstance(node, dict)):
                raise ValueError('ASAR member path is invalid.')
            relative = f'{prefix}/{name}' if prefix else name
            if isinstance(node.get('files'), dict):
                visit(node, relative)
            else:
                result.append(relative)

    visit(header)
    return tuple(sorted(result))


def read_asar_members(archive: Path, names: Iterable[str]) -> dict[str, bytes]:
    """Read named regular packed members after validating their bounds."""
    archive, header, data_offset, archive_size = _read_header(archive)
    result = {}
    with archive.open('rb') as stream:
        for name in names:
            node = _member_node(header, name)
            offset = node.get('offset')
            size = node.get('size')
            if isinstance(offset, str):
                try:
                    offset = int(offset)
                except ValueError as exc:
                    raise ValueError(f'ASAR member offset is invalid: {name}') from exc
            if (node.get('unpacked') or 'link' in node or
                    not isinstance(offset, int) or isinstance(offset, bool) or offset < 0 or
                    not isinstance(size, int) or isinstance(size, bool) or size < 0 or
                    size > MAX_MEMBER_SIZE or data_offset + offset + size > archive_size):
                raise ValueError(f'ASAR member is invalid or out of bounds: {name}')
            stream.seek(data_offset + offset)
            content = stream.read(size)
            if len(content) != size:
                raise ValueError(f'ASAR member is truncated: {name}')
            result[name] = content
    return result
