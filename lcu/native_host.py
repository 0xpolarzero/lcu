#!/usr/bin/env python3
"""Relay the original Chrome native host with LCU's local agent-header policy.

LCU always enables the official extension's browser-agent request header. This
lets the original browser service use Chrome without a Codex account while the
extension still labels requests from agent-controlled tabs. All other native
messages pass through unchanged to the installed application's original host.
"""

import json
from pathlib import Path
import platform
import struct
import subprocess
import sys
import threading


MAX_MESSAGE_BYTES = 64 * 1024 * 1024


def _read_frame(stream):
    prefix = stream.read(4)
    if not prefix:
        return None
    if len(prefix) != 4:
        raise ValueError('Short native-message length')
    size = struct.unpack('<I', prefix)[0]
    if size > MAX_MESSAGE_BYTES:
        raise ValueError('Native message exceeds the supported size')
    payload = stream.read(size)
    if len(payload) != size:
        raise ValueError('Short native-message body')
    return payload


def _write_frame(stream, payload):
    stream.write(struct.pack('<I', len(payload)))
    stream.write(payload)
    stream.flush()


def _enable_agent_header(payload):
    try:
        message = json.loads(payload)
    except (UnicodeDecodeError, ValueError):
        return payload
    if not isinstance(message, dict):
        return payload
    result = message.get('result')
    if (not isinstance(result, dict) or result.get('type') != 'extension' or
            result.get('agentRequestHeaderEnabled') is not False):
        return payload
    result['agentRequestHeaderEnabled'] = True
    return json.dumps(message, ensure_ascii=False, separators=(',', ':')).encode()


def _relay(source, destination, transform=None):
    while (payload := _read_frame(source)) is not None:
        _write_frame(destination, transform(payload) if transform else payload)


def _original_host():
    arch = {'aarch64': 'arm64', 'arm64': 'arm64', 'x86_64': 'x64', 'amd64': 'x64'}.get(platform.machine())
    if arch is None or platform.system() != 'Linux':
        raise ValueError('The Chrome native host requires Linux ARM64 or x86-64')
    binary = Path(__file__).resolve().parent / 'chrome/extension-host/linux' / arch / 'extension-host'
    if not binary.is_file():
        raise ValueError(f'The original Chrome native host is missing: {binary}')
    return binary


def main():
    child = subprocess.Popen([str(_original_host()), *sys.argv[1:]],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    errors = []

    def inbound():
        try:
            _relay(sys.stdin.buffer, child.stdin, _enable_agent_header)
        except (OSError, ValueError) as exc:
            errors.append(exc)
            if child.poll() is None:
                child.terminate()
        finally:
            child.stdin.close()

    reader = threading.Thread(target=inbound, daemon=True)
    reader.start()
    try:
        _relay(child.stdout, sys.stdout.buffer)
    except (OSError, ValueError) as exc:
        errors.append(exc)
        if child.poll() is None:
            child.terminate()
    reader.join(timeout=1)
    status = child.wait()
    if errors:
        print(f'LCU Chrome native-host relay failed: {errors[0]}', file=sys.stderr)
        return 1
    return status


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        sys.exit(f'LCU Chrome native-host relay failed: {exc}')
