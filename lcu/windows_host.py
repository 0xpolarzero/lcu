"""Extract the unchanged original Windows pipe host into a private generation.

Only the tiny launch entry is LCU code. The native host and its dependencies
come unchanged from the installed application's verified app.asar.
"""

from __future__ import annotations

import json
import posixpath
from pathlib import Path
from queue import Empty, Queue
import re
import subprocess
from threading import Thread

from .asar import list_asar_members, read_asar_members

_MAIN_PATH = re.compile(r'^\.vite/build/main(?:-[^/]+)?\.js$')
_BINDING = re.compile(r"(?<![\w$])([A-Za-z_$][\w$]*)\s*=\s*require\s*\(\s*(['\"])([^'\"]+)\2\s*\)")


def _required_layout(detail: str):
    raise ValueError(f'Required Windows host layout is unavailable: {detail}')


def _skip_quoted(source: str, index: int, quote: str) -> int:
    index += 1
    while index < len(source):
        if source[index] == '\\':
            index += 2
        elif source[index] == quote:
            return index + 1
        else:
            index += 1
    _required_layout('unterminated source string')


def _function_body_end(source: str, opening: int) -> int:
    """Find the Wre factory's end; skip strings, comments, and regex literals."""
    depth = 1
    index = opening + 1
    modes = ['code']
    interpolation_depths = []
    while index < len(source):
        mode = modes[-1]
        char = source[index]
        if mode == 'template':
            if char == '\\':
                index += 2
            elif char == '`':
                modes.pop()
                index += 1
            elif source.startswith('${', index):
                depth += 1
                interpolation_depths.append(depth)
                modes.append('code')
                index += 2
            else:
                index += 1
            continue
        if char in "'\"":
            index = _skip_quoted(source, index, char)
        elif char == '`':
            modes.append('template')
            index += 1
        elif source.startswith('//', index):
            newline = source.find('\n', index + 2)
            index = len(source) if newline < 0 else newline + 1
        elif source.startswith('/*', index):
            end = source.find('*/', index + 2)
            if end < 0:
                _required_layout('unterminated source comment')
            index = end + 2
        elif char == '/' and _starts_regex(source, index):
            index = _regex_end(source, index)
        elif char == '{':
            depth += 1
            index += 1
        elif char == '}':
            prior = depth
            depth -= 1
            index += 1
            if interpolation_depths and prior == interpolation_depths[-1]:
                interpolation_depths.pop()
                modes.pop()
            elif depth == 0:
                return index
        else:
            index += 1
    _required_layout('unterminated Wre function')


def _starts_regex(source: str, index: int) -> bool:
    previous = index - 1
    while previous >= 0 and source[previous].isspace():
        previous -= 1
    if previous >= 0 and source[previous] in '=(:,[!&|?;{}+-*%^~<>':
        return True
    word = re.search(r'([A-Za-z_$][\w$]*)\s*$', source[:index])
    return bool(word and word.group(1) in ('return', 'throw', 'case', 'delete', 'void', 'typeof'))


def _regex_end(source: str, index: int) -> int:
    index += 1
    in_class = False
    escaped = False
    while index < len(source) and source[index] not in '\r\n':
        char = source[index]
        if escaped:
            escaped = False
        elif char == '\\':
            escaped = True
        elif char == '[':
            in_class = True
        elif char == ']':
            in_class = False
        elif char == '/' and not in_class:
            index += 1
            while index < len(source) and source[index].isalpha():
                index += 1
            return index
        index += 1
    _required_layout('unterminated Wre regular expression')


def _wre_source(source: bytes) -> bytes:
    try:
        text = source.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ValueError('Required Windows host layout is unavailable: main source is not UTF-8.') from exc
    matches = list(re.finditer(r'\bfunction\s+Wre\s*\(', text))
    if len(matches) != 1:
        _required_layout('expected one named Wre host factory')
    match = matches[0]
    index = match.end()
    parens = 1
    while index < len(text) and parens:
        char = text[index]
        if char in "'\"`":
            index = _skip_quoted(text, index, char)
        elif text.startswith('//', index):
            newline = text.find('\n', index + 2)
            index = len(text) if newline < 0 else newline + 1
        elif text.startswith('/*', index):
            end = text.find('*/', index + 2)
            if end < 0:
                _required_layout('unterminated function parameter comment')
            index = end + 2
        elif char == '(':
            parens += 1
            index += 1
        elif char == ')':
            parens -= 1
            index += 1
        else:
            index += 1
    while index < len(text) and text[index].isspace():
        index += 1
    if parens or index >= len(text) or text[index] != '{':
        _required_layout('Wre is not a function declaration')
    end = _function_body_end(text, index)
    result = text[match.start():end].encode('utf-8')
    if b'closeActiveTurn' not in result or b'nativePipeDirectory' not in result:
        _required_layout('Wre no longer exposes the expected native-pipe and turn-cleanup interface')
    return result


def _referenced(name: str, source: bytes) -> bool:
    try:
        text = source.decode('utf-8')
    except UnicodeDecodeError:
        return False
    return re.search(r'(?<![\w$])' + re.escape(name) + r'(?![\w$])', text) is not None


def _direct_member(current: str, specifier: str, members: set[str]):
    if specifier.startswith('node:'):
        return None
    if not specifier.startswith('.'):
        _required_layout(f'unsupported non-relative original dependency {specifier!r}')
    target = posixpath.normpath(posixpath.join(posixpath.dirname(current), specifier))
    if target not in members:
        _required_layout(f'original dependency is missing: {target}')
    return target


def _host_imports(main: bytes, host: bytes) -> list[tuple[str, str]]:
    bindings = {}
    for match in _BINDING.finditer(main.decode('utf-8')):
        name, specifier = match.group(1), match.group(3)
        if not _referenced(name, host):
            continue
        if name in ('c', 'T', 'p', 'v', '_', 'R'):
            continue
        if name not in ('n', 'r'):
            _required_layout(f'unsupported original import binding {name}')
        previous = bindings.setdefault(name, specifier)
        if previous != specifier:
            _required_layout(f'ambiguous imported binding {name}')
    for name in ('n', 'r'):
        if _referenced(name, host) and name not in bindings:
            _required_layout(f'original Wre import {name} is missing')
    if not bindings:
        _required_layout('no supported original module import supplies Wre')
    return sorted(bindings.items())


def _original_members(archive: Path) -> tuple[bytes, list[tuple[str, str]], dict[str, bytes]]:
    members = set(list_asar_members(archive))
    mains = sorted(name for name in members if _MAIN_PATH.fullmatch(name))
    matches = []
    for name in mains:
        source = read_asar_members(archive, (name,))[name]
        try:
            host = _wre_source(source)
        except ValueError as exc:
            if str(exc).endswith('expected one named Wre host factory'):
                continue
            raise
        matches.append((name, source, host))
    if len(matches) != 1:
        _required_layout('expected one main bundle with a unique Wre host factory')
    name, main, host = matches[0]
    bound_imports = _host_imports(main, host)
    imports = []
    names = []
    for alias, specifier in bound_imports:
        member = _direct_member(name, specifier, members)
        if member is None:
            imports.append((alias, specifier))
        else:
            imports.append((alias, './' + member))
            names.append(member)
    # Preserve the original host's small dependency families. Chunk hashes are
    # discovered from this app; no transitive module graph or package resolver
    # is inferred here.
    names.extend(sorted(member for member in members
                        if re.fullmatch(r'\.vite/build/(?:rolldown-runtime|src|logger)-[^/]+\.js', member)))
    names.extend(('node_modules/tslib/package.json', 'node_modules/tslib/tslib.js'))
    missing = [member for member in names if member not in members]
    if missing:
        _required_layout(f'original host dependency is missing: {missing[0]}')
    contents = read_asar_members(archive, tuple(dict.fromkeys(names)))
    return host, imports, contents


def materialize_original_host(app: Path, destination: Path) -> Path:
    """Extract the unique structurally compatible Wre host and exact dependencies."""
    archive = app / 'app/resources/app.asar'
    if archive.is_symlink() or not archive.is_file():
        _required_layout('app/resources/app.asar is missing or redirected')
    fragment, imports, contents = _original_members(archive)
    template = Path(__file__).with_name('windows_host_entry.cjs').read_bytes()
    imports_marker = b'// ORIGINAL_WINDOWS_HOST_IMPORTS'
    host_marker = b'// ORIGINAL_WINDOWS_PIPE_HOST'
    if template.count(imports_marker) != 1 or template.count(host_marker) != 1:
        raise ValueError('Windows host entry markers are missing or ambiguous.')
    import_source = '\n'.join(
        f'const {name} = require({json.dumps(specifier)});' for name, specifier in imports
    ).encode('utf-8')
    entry = template.replace(imports_marker, import_source).replace(host_marker, fragment)
    destination.mkdir(parents=True, exist_ok=False)
    for name, content in contents.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    launcher = destination / 'windows-pipe-host.cjs'
    launcher.write_bytes(entry)
    for source, target in (
        ('windows_lifetime_host.cjs', 'windows-lifetime-host.cjs'),
        ('windows_sky_service.mjs', 'windows-sky-service.mjs'),
    ):
        (destination / target).write_bytes(Path(__file__).with_name(source).read_bytes())
    return launcher


def start_original_host(*, node: Path, entry: Path, helper: Path, transport: Path,
                        env: dict[str, str]) -> tuple[subprocess.Popen, str, str]:
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
        lifetime = state.get('lifetimePath') if isinstance(state, dict) else None
        if (not isinstance(state, dict) or state.get('ready') is not True or
                not isinstance(pipe, str) or
                not pipe.startswith('\\\\.\\pipe\\lcu-wre-') or len(pipe) > 256 or
                not isinstance(lifetime, str) or
                not lifetime.startswith('\\\\.\\pipe\\lcu-lifetime-') or len(lifetime) > 256):
            raise ValueError('Original Windows native host did not report its private pipes.')
        return process, pipe, lifetime
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
