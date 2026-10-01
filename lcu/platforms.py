"""Validate an installed official application for the original CUA runtime."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import platform as host_platform
import plistlib
import re
import stat
import subprocess

from .app_layout import locate_codex_tools
from .asar import read_asar_members


MAC_BUNDLE_ID = 'com.openai.codex'
MAC_HELPER_ID = 'com.openai.sky.CUAService'
OPENAI_TEAM_ID = '2DC432GLL2'
MAC_HELPER = Path('Resources/cua_node/lib/node_modules/@oai/sky/Codex Computer Use.app')
MAC_REQUIRED_FILES = (
    'Resources/cua_node/bin/node',
    'Resources/cua_node/bin/node_repl',
    'Resources/cua_node/lib/node_modules/@oai/cua-repl/bin/cua-repl.mjs',
    'Resources/plugins/openai-bundled/plugins/unified-computer-use/.mcp.json',
    'Resources/plugins/openai-bundled/plugins/chrome/.codex-plugin/plugin.json',
)
MAC_EXECUTABLES = (
    'Resources/cua_node/bin/node',
    'Resources/cua_node/bin/node_repl',
)


@dataclass(frozen=True)
class InstalledApplication:
    app: Path
    resources: Path
    runtime: Path
    backend: str
    version: str
    arch: str
    codex_cli: Path
    code_mode_host: Path
    runtime_version: str


def _identity(bundle: Path, identifier: str) -> dict:
    info = bundle / 'Contents/Info.plist'
    if not info.is_file() or info.is_symlink():
        raise ValueError(f'Application bundle metadata is missing: {info}')
    with info.open('rb') as source:
        details = plistlib.load(source)
    if details.get('CFBundleIdentifier') != identifier:
        raise ValueError(f'Unexpected application bundle identifier: {bundle}')
    return details


def _verify_signature(bundle: Path, identifier: str) -> None:
    # `codesign` verifies sealed resources and nested code in place. The
    # installed app and signed helper are never copied or modified by LCU.
    verified = subprocess.run(
        ['codesign', '--verify', '--deep', '--strict', str(bundle)],
        capture_output=True, text=True, check=False, timeout=120,
    )
    if verified.returncode:
        detail = (verified.stderr or verified.stdout).strip().replace('\n', ' ')[:300]
        raise ValueError(f'Installed application signature verification failed: {bundle}: {detail}')
    identity = subprocess.run(
        ['codesign', '-dv', '--verbose=2', str(bundle)],
        capture_output=True, text=True, check=False, timeout=30,
    )
    if (identity.returncode or
            f'Identifier={identifier}' not in identity.stderr.splitlines() or
            f'TeamIdentifier={OPENAI_TEAM_ID}' not in identity.stderr.splitlines()):
        raise ValueError(f'Installed application signer does not match OpenAI: {bundle}')


def resolve_installed_mac_app(app_path: Path, *, arch: str | None = None) -> InstalledApplication:
    """Validate a local ChatGPT.app without relocating or modifying signed files."""
    if host_platform.system() != 'Darwin':
        raise ValueError('The macOS application can only be validated on macOS')
    app = Path(app_path).expanduser()
    if app.is_symlink() or not app.is_dir() or app.name != 'ChatGPT.app':
        raise ValueError(f'Expected a local ChatGPT.app directory: {app}')
    app = app.resolve(strict=True)
    architecture = arch or {'arm64': 'arm64', 'aarch64': 'arm64', 'x86_64': 'x64'}.get(host_platform.machine())
    if architecture not in ('arm64', 'x64'):
        raise ValueError(f'Unsupported macOS architecture: {architecture}')
    contents = app / 'Contents'
    resources = contents / 'Resources'
    runtime = resources / 'cua_node'
    details = _identity(app, MAC_BUNDLE_ID)
    version = details.get('CFBundleShortVersionString')
    if not isinstance(version, str) or not version.strip():
        raise ValueError(f'Installed application version is missing: {app}')
    helper = contents / MAC_HELPER
    _identity(helper, MAC_HELPER_ID)
    manifest_path = runtime / 'manifest.json'
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError('Installed application CUA manifest is missing')
    manifest = json.loads(manifest_path.read_text())
    runtime_version = manifest.get('runtime_archive_version')
    if (manifest.get('platform') != 'darwin' or manifest.get('arch') != architecture or
            not isinstance(runtime_version, str) or not runtime_version.strip()):
        raise ValueError('Installed application CUA runtime has an incompatible platform or architecture')
    for relative in MAC_REQUIRED_FILES:
        file = contents / relative
        if not file.is_file() or file.is_symlink():
            raise ValueError(f'Required application file is missing or invalid: {relative}')
        if relative in MAC_EXECUTABLES and not os.access(file, os.X_OK):
            raise ValueError(f'Installed application executable is not executable: {relative}')
    tools = locate_codex_tools(resources)
    for executable in (tools.cli, tools.code_mode_host):
        if not os.access(executable, os.X_OK):
            raise ValueError(f'Installed application executable is not executable: {executable.relative_to(contents)}')
    _verify_signature(app, MAC_BUNDLE_ID)
    _verify_signature(helper, MAC_HELPER_ID)
    return InstalledApplication(app, resources, runtime, 'mac', version, architecture,
                                tools.cli, tools.code_mode_host, runtime_version)


LINUX_APP_PATH = Path('/usr/lib/chatgpt')
_VERSION = re.compile(r'[A-Za-z0-9][A-Za-z0-9.+:~_-]*')


def _linux_version(app: Path, arch: str) -> str:
    """Read the selected app version, or confirm that dpkg owns its exact path."""
    try:
        package = json.loads(read_asar_members(app / 'resources/app.asar', ('package.json',))['package.json'])
        version = package.get('version')
        if isinstance(version, str) and _VERSION.fullmatch(version):
            return version
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        pass
    executable = app / 'ChatGPT'
    try:
        ownership = subprocess.run(['dpkg-query', '-S', '--', str(executable)],
                                   check=True, capture_output=True, text=True, timeout=20)
        owners = [owner for owner, separator, path in
                  (line.partition(': ') for line in ownership.stdout.splitlines())
                  if separator and Path(path) == executable and owner.split(':', 1)[0] == 'chatgpt']
        if len(owners) != 1:
            raise ValueError('No unique chatgpt package owns the selected executable path')
        fields = subprocess.run(['dpkg-query', '-W', '--showformat=%v %a', owners[0]],
                                check=True, capture_output=True, text=True, timeout=20).stdout.split()
        expected_arch = 'arm64' if arch == 'arm64' else 'amd64'
        if len(fields) != 2 or fields[1] != expected_arch:
            raise ValueError('The selected dpkg-owned ChatGPT path has the wrong architecture')
        if _VERSION.fullmatch(fields[0]):
            return fields[0]
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError('Cannot determine the selected app version from app.asar or its dpkg-owned path') from exc
    raise ValueError('Cannot determine the selected app version from app.asar or its dpkg-owned path')


def _within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _untrusted_entry(path: Path, info: os.stat_result, trusted: set[int]) -> str | None:
    """Why this entry lets another account change what the desktop account executes."""
    if info.st_uid not in trusted:
        return f'owned by uid {info.st_uid}'
    writable = info.st_mode & stat.S_IWOTH or (info.st_mode & stat.S_IWGRP and info.st_gid != 0)
    if writable and not (stat.S_ISDIR(info.st_mode) and info.st_mode & stat.S_ISVTX):
        # A sticky directory (like /tmp) only lets accounts add entries; they cannot
        # replace ones owned by someone else.
        return 'writable by group or other accounts'
    return None


def _read_only_mount(path: Path) -> bool:
    try:
        return bool(os.statvfs(path).f_flag & os.ST_RDONLY)
    except OSError:
        return False


def _check_trusted_tree(app: Path, runtime: Path, files: tuple[Path, ...], trusted: set[int]) -> None:
    """Refuse a tree where accounts other than root and the desktop account could replace code.

    Covers the executables and modules the runtime launches, every directory above them up to
    `/`, and the CUA runtime tree. Content on a read-only mount is not writable by anyone.
    """
    problems = []
    checked = set()

    def check(path: Path, info=None):
        if path in checked:
            return
        checked.add(path)
        info = info or path.lstat()
        if stat.S_ISLNK(info.st_mode):
            real = path.resolve()
            if not _within(real, app):
                problems.append(f'{path} links outside the application ({real})')
            return
        if _read_only_mount(path):
            return
        reason = _untrusted_entry(path, info, trusted)
        if reason:
            problems.append(f'{path} is {reason}')

    for path in files:
        real = path.resolve(strict=True)
        if not _within(real, app):
            problems.append(f'{path} resolves outside the application ({real})')
            continue
        for candidate in (real, *real.parents):
            check(candidate)
    for directory, directories, names in os.walk(runtime):
        for name in (*directories, *names):
            check(Path(directory) / name)
    if problems:
        shown = '; '.join(problems[:3]) + (f'; and {len(problems) - 3} more' if len(problems) > 3 else '')
        raise ValueError('The application is not in a location only root and this account can change: '
                         f'{shown}. Install the app with a package manager or make it root-owned and not '
                         'writable by other accounts')


def resolve_installed_linux_app(app_path: Path, *, arch: str,
                               trusted_uids: set[int] | None = None) -> InstalledApplication:
    """Validate an installed ChatGPT Linux app in place, without copying or modifying it."""
    app = Path(app_path).expanduser()
    if not app.is_dir():
        raise ValueError(f'Expected an installed ChatGPT application directory: {app}')
    app = app.resolve(strict=True)
    resources = app / 'resources'
    runtime = resources / 'cua_node'
    manifest_path = runtime / 'manifest.json'
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError(f'Application runtime manifest is missing: {manifest_path}')
    manifest = json.loads(manifest_path.read_text())
    runtime_version = manifest.get('runtime_archive_version')
    if (manifest.get('platform') != 'linux' or manifest.get('arch') != arch or
            not isinstance(runtime_version, str) or not runtime_version.strip()):
        raise ValueError('Application runtime manifest has an unsupported platform, architecture, or version')
    tools = locate_codex_tools(resources)
    extension_host = resources / f'plugins/openai-bundled/plugins/chrome/extension-host/linux/{arch}/extension-host'
    required = (
        app / 'ChatGPT', runtime / 'bin/node', runtime / 'bin/node_repl',
        runtime / 'lib/node_modules/@oai/cua-repl/bin/cua-repl.mjs',
        tools.cli, tools.code_mode_host, resources / 'app.asar',
        resources / 'plugins/openai-bundled/plugins/chrome/.codex-plugin/plugin.json',
        extension_host,
        resources / 'plugins/openai-bundled/plugins/unified-computer-use/.mcp.json',
    )
    missing = [str(path) for path in required if path.is_symlink() or not path.is_file()]
    browser_plugin = resources / 'plugins/openai-bundled/plugins/browser'
    if browser_plugin.is_symlink() or not browser_plugin.is_dir():
        missing.append(str(browser_plugin))
    if missing:
        raise ValueError('Application payload is incomplete: ' + ', '.join(missing))
    for path in (app / 'ChatGPT', runtime / 'bin/node', runtime / 'bin/node_repl',
                 tools.cli, tools.code_mode_host, extension_host):
        if not os.access(path, os.X_OK):
            raise ValueError(f'Application executable is not executable: {path}')
    trusted = {0, os.getuid(), os.geteuid()} | set(trusted_uids or ())
    modules = runtime / 'lib/node_modules'
    _check_trusted_tree(app, runtime.resolve(strict=True),
                        (*required, *((modules,) if modules.exists() else ())), trusted)
    return InstalledApplication(app, resources, runtime, 'linux', _linux_version(app, arch), arch,
                                tools.cli, tools.code_mode_host, runtime_version)
