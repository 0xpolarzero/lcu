"""Extract the pinned original Windows pipe host into a private generation.

Only the tiny launch entry is LCU code. The native host and its dependencies
come unchanged from the installed application's verified app.asar.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from queue import Empty, Queue
import struct
import subprocess
from threading import Thread


MAIN = '.vite/build/main-BR_2NHW6.js'
MAIN_SHA256 = '1f2b91cf92fc023fb2fa41e1c1d03698fa6e37354ecd07dd0cebd21337607b08'
HOST_START = 155346
HOST_END = 165208
HOST_SHA256 = '3dae7a2bb89573e78dff25715efaf44dadbe7a7376c9243987d18d43b5f05247'
ORIGINAL_FILES = (
    '.vite/build/rolldown-runtime-CPUxUITh.js',
    '.vite/build/src-DldfpmrL.js',
    '.vite/build/src-C9YLnbgY.js',
    '.vite/build/logger-DkO6GWbX.js',
    'node_modules/tslib/package.json',
    'node_modules/tslib/tslib.js',
)
MARKER = b'// ORIGINAL_WINDOWS_PIPE_HOST'


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _asar_members(archive: Path, names: tuple[str, ...]) -> dict[str, bytes]:
    with archive.open('rb') as stream:
        preamble = stream.read(16)
        if len(preamble) != 16:
            raise ValueError('Pinned Windows app.asar header is truncated.')
        size_payload, header_size, header_payload, json_size = struct.unpack('<4I', preamble)
        data_offset = 8 + header_size
        if (size_payload != 4 or header_payload != header_size - 4 or
                json_size > header_payload - 4 or json_size > 64 * 1024 * 1024 or
                data_offset > archive.stat().st_size):
            raise ValueError('Pinned Windows app.asar header is invalid.')
        header = json.loads(stream.read(json_size))
        result = {}
        for name in names:
            node = header
            try:
                for part in name.split('/'):
                    node = node['files'][part]
                offset, size = int(node['offset']), node['size']
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f'Pinned Windows app.asar member is missing: {name}') from exc
            if (node.get('unpacked') or 'link' in node or not isinstance(size, int) or
                    isinstance(size, bool) or size < 0 or size > 8 * 1024 * 1024 or
                    offset < 0 or data_offset + offset + size > archive.stat().st_size):
                raise ValueError(f'Pinned Windows app.asar member is invalid: {name}')
            stream.seek(data_offset + offset)
            content = stream.read(size)
            if len(content) != size:
                raise ValueError(f'Pinned Windows app.asar member is truncated: {name}')
            result[name] = content
        return result


def materialize_original_host(app: Path, destination: Path, *, expected_asar_sha256: str) -> Path:
    """Write exact pinned app code plus a thin launch entry inside a managed generation."""
    archive = app / 'app/resources/app.asar'
    if archive.is_symlink() or not archive.is_file() or _digest(archive) != expected_asar_sha256:
        raise ValueError('Selected Windows app.asar does not match the official package pin.')
    contents = _asar_members(archive, (MAIN, *ORIGINAL_FILES))
    main = contents.pop(MAIN)
    fragment = main[HOST_START:HOST_END]
    if (hashlib.sha256(main).hexdigest() != MAIN_SHA256 or
            hashlib.sha256(fragment).hexdigest() != HOST_SHA256):
        raise ValueError('Pinned Windows native-pipe host source changed.')
    template = Path(__file__).with_name('windows_host_entry.cjs').read_bytes()
    if template.count(MARKER) != 1:
        raise ValueError('Windows host entry marker is missing or ambiguous.')
    entry = template.replace(MARKER, fragment)
    destination.mkdir(parents=True, exist_ok=False)
    for name, content in contents.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    launcher = destination / 'windows-pipe-host.cjs'
    launcher.write_bytes(entry)
    return launcher


def start_original_host(*, node: Path, entry: Path, helper: Path, transport: Path,
                        env: dict[str, str]) -> tuple[subprocess.Popen, str]:
    """Start the extracted original host and wait for its actual pipe readiness."""
    if not all(path.is_file() for path in (node, entry, helper, transport)):
        raise ValueError('The selected original Windows native host is incomplete.')
    child_env = dict(env)
    child_env['LCU_WRE_HELPER_PATH'] = str(helper)
    child_env['LCU_WRE_TRANSPORT_PATH'] = str(transport)
    process = subprocess.Popen([str(node), str(entry)], cwd=entry.parent, env=child_env,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    ready = Queue(maxsize=1)
    Thread(target=lambda: ready.put(process.stdout.readline()), daemon=True).start()
    try:
        line = ready.get(timeout=15)
        state = json.loads(line)
        pipe = state.get('pipePath') if isinstance(state, dict) else None
        if (not isinstance(state, dict) or state.get('ready') is not True or
                not isinstance(pipe, str) or
                not pipe.startswith('\\\\.\\pipe\\lcu-wre-') or len(pipe) > 256):
            raise ValueError('Original Windows native host did not report its private pipe.')
        return process, pipe
    except (Empty, ValueError, json.JSONDecodeError) as exc:
        stop_original_host(process, require_success=False)
        raise ValueError('Original Windows native host failed to become ready.') from exc


def stop_original_host(process: subprocess.Popen, *, require_success=True) -> None:
    """Dispose only the host process owned by this LCU MCP connection."""
    if process.stdin and not process.stdin.closed:
        process.stdin.close()
    try:
        try:
            status = process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
            status = process.wait(timeout=5)
    finally:
        if process.stdout:
            process.stdout.close()
    if require_success and status != 0:
        raise ValueError(f'Original Windows native host exited with status {status}.')
