"""Supervise the original macOS client turn-ended command for one MCP process."""
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import sys
import tempfile
from threading import Thread
from queue import Empty, Queue


def turn_ended_payload(session_id, turn_id):
    return json.dumps({
        'type': 'agent-turn-complete',
        'thread-id': session_id,
        'turn-id': turn_id,
    }, separators=(',', ':'))


def start_original_host(*, python, client: Path, entry: Path, env: dict[str, str]):
    """Start a private Unix-socket bridge and wait for its readiness record."""
    if not client.is_file() or not os.access(client, os.X_OK) or not entry.is_file():
        raise ValueError('The selected original macOS computer-use client is incomplete.')
    socket_dir = '/private/tmp' if Path('/private/tmp').is_dir() else None
    temporary = tempfile.TemporaryDirectory(prefix='lcu-ml-', dir=socket_dir)
    address = str(Path(temporary.name) / 'lifetime.sock')
    process = subprocess.Popen([str(python), '-B', str(entry), 'serve', address, str(client)],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               env=env)
    ready = Queue(maxsize=1)
    Thread(target=lambda: ready.put(process.stdout.readline()), daemon=True).start()
    try:
        line = ready.get(timeout=5)
        state = json.loads(line)
        if state != {'ready': True, 'socket': address}:
            raise ValueError('Original macOS lifecycle host reported an invalid socket.')
        return process, temporary, address
    except (Empty, ValueError, json.JSONDecodeError) as exc:
        stop_original_host(process, temporary, require_success=False)
        raise ValueError('Original macOS lifecycle host failed to become ready.') from exc


def stop_original_host(process, temporary, *, require_success=True):
    """Dispose only the lifetime host owned by this LCU MCP connection."""
    if process.stdin and not process.stdin.closed:
        process.stdin.close()
    try:
        try:
            status = process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            status = process.wait(timeout=2)
    finally:
        if process.stdout:
            process.stdout.close()
        temporary.cleanup()
    if require_success and status != 0:
        raise ValueError(f'Original macOS lifecycle host exited with status {status}.')


def serve(address, client):
    """Accept bounded ID pairs and invoke the original signed client command."""
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(address)
    os.chmod(address, 0o600)
    server.listen(8)
    print(json.dumps({'ready': True, 'socket': address}), flush=True)
    try:
        while True:
            readable, _, _ = select.select([server, sys.stdin], [], [])
            if sys.stdin in readable and not sys.stdin.readline():
                break
            if server not in readable:
                continue
            connection, _ = server.accept()
            with connection:
                connection.settimeout(3)
                try:
                    raw = bytearray()
                    while len(raw) <= 4096 and b'\n' not in raw:
                        part = connection.recv(1024)
                        if not part:
                            break
                        raw.extend(part)
                    if len(raw) > 4096 or b'\n' not in raw:
                        raise ValueError('Invalid macOS cleanup request size or framing.')
                    request = json.loads(raw.split(b'\n', 1)[0])
                    session_id = request.get('session_id') if isinstance(request, dict) else None
                    turn_id = request.get('turn_id') if isinstance(request, dict) else None
                    if (not isinstance(session_id, str) or not session_id.strip() or
                            not isinstance(turn_id, str) or not turn_id.strip()):
                        raise ValueError('Original macOS turn IDs are missing.')
                    payload = turn_ended_payload(session_id, turn_id)
                    result = subprocess.run([client, 'turn-ended', payload],
                                            stdin=subprocess.DEVNULL,
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            timeout=3, check=False)
                    if result.returncode != 0:
                        raise RuntimeError(f'Original turn-ended command exited with status {result.returncode}.')
                    response = {'notified': True}
                except Exception as exc:
                    response = {'notified': False, 'error': str(exc)[:512]}
                    print(f'LCU macOS turn cleanup failed: {response["error"]}', file=sys.stderr, flush=True)
                try:
                    connection.sendall((json.dumps(response, separators=(',', ':')) + '\n').encode())
                except OSError:
                    # A disconnected hook client must not terminate the host.
                    continue
    finally:
        server.close()
        Path(address).unlink(missing_ok=True)


if __name__ == '__main__' and len(sys.argv) == 4 and sys.argv[1] == 'serve':
    serve(sys.argv[2], sys.argv[3])
