"""Select an intact, installed official Windows ChatGPT package in place.

Windows owns MSIX deployment and its protected package directory. LCU reads the
current user's registered package; it never extracts or changes app files.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import platform
import subprocess
from typing import Mapping


PACKAGE_NAME = 'OpenAI.Codex'
PACKAGE_PUBLISHER = 'CN=50BDFD77-8903-4850-9FFE-6E8522F64D5B'
WINDOWS_REQUIRED_FILES = (
    'app/ChatGPT.exe',
    'app/resources/app.asar',
    'app/resources/cua_node/bin/node.exe',
    'app/resources/cua_node/bin/node_repl.exe',
    'app/resources/cua_node/manifest.json',
    'app/resources/cua_node/bin/node_modules/@oai/cua-repl/bin/cua-repl.mjs',
    'app/resources/cua_node/bin/node_modules/@oai/sky/bin/windows/codex-computer-use.exe',
    'app/resources/cua_node/bin/node_modules/@oai/sky/bin/windows/swift/x64/codex-computer-use-swift.exe',
    'app/resources/codex.exe',
    'app/resources/codex-code-mode-host.exe',
    'app/resources/plugins/openai-bundled/plugins/chrome/.codex-plugin/plugin.json',
    'app/resources/plugins/openai-bundled/plugins/chrome/extension-host/windows/x64/extension-host.exe',
    'app/resources/plugins/openai-bundled/plugins/unified-computer-use/.mcp.json',
)


@dataclass(frozen=True)
class InstalledWindowsApplication:
    app: Path
    resources: Path
    runtime: Path
    launcher: Path
    backend: str
    version: str
    arch: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _registered_package():
    # Get-AppxPackage only sees packages registered for this account. Use its
    # InstallLocation rather than guessing the WindowsApps package volume.
    command = (
        "$ErrorActionPreference='Stop'; "
        "$packages=@(Get-AppxPackage -Name 'OpenAI.Codex'); "
        "$packages | Select-Object Name,Publisher,Version,Architecture,InstallLocation "
        '| ConvertTo-Json -Compress'
    )
    result = subprocess.run(
        ['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', command],
        check=True, capture_output=True, text=True, timeout=30,
    )
    if not result.stdout.strip():
        raise ValueError('Install the official ChatGPT MSIX for this Windows account first.')
    parsed = json.loads(result.stdout)
    packages = parsed if isinstance(parsed, list) else [parsed]
    if len(packages) != 1 or not isinstance(packages[0], dict):
        raise ValueError('Expected exactly one registered OpenAI.Codex package for this account.')
    return packages[0]


def _component(app: Path, relative: str) -> Path:
    expected = app / relative
    if expected.is_file():
        return expected
    # MSIX stores `@` as `%40` in its OPC archive. Accept either spelling in
    # the deployed package, but no arbitrary path fallback.
    encoded = app / relative.replace('@oai/', '%40oai/')
    return encoded if encoded.is_file() else expected


def resolve_installed_windows_app(*, expected_version: str, expected_runtime: str,
                                  expected_hashes: Mapping[str, str]) -> InstalledWindowsApplication:
    """Validate the current user's pinned, registered Windows x64 package."""
    if platform.system() != 'Windows' or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise ValueError('The Windows application can only be validated on Windows x64.')
    if not expected_version or not expected_runtime:
        raise ValueError('A pinned application version and runtime are required.')
    if set(expected_hashes) != set(WINDOWS_REQUIRED_FILES):
        raise ValueError('Windows application pins must cover every required runtime file.')
    if any(len(value) != 64 or any(char not in '0123456789abcdef' for char in value)
           for value in expected_hashes.values()):
        raise ValueError('Windows application pins must contain SHA-256 hex digests.')
    package = _registered_package()
    if (package.get('Name') != PACKAGE_NAME or package.get('Publisher') != PACKAGE_PUBLISHER or
            str(package.get('Version')) != expected_version or
            str(package.get('Architecture')).lower() not in ('x64', 'amd64')):
        raise ValueError('Registered ChatGPT package does not match the Windows x64 pin.')
    selected = package.get('InstallLocation')
    if not isinstance(selected, str) or not selected:
        raise ValueError('Registered ChatGPT package has no install location.')
    app = Path(selected)
    if app.is_symlink() or not app.is_dir():
        raise ValueError('Registered ChatGPT package directory is missing or redirected.')
    app = app.resolve(strict=True)
    resources = app / 'app/resources'
    runtime = resources / 'cua_node'
    for relative in WINDOWS_REQUIRED_FILES:
        file = _component(app, relative)
        if not file.is_file() or file.is_symlink() or _sha256(file) != expected_hashes[relative]:
            raise ValueError(f'Installed Windows application file does not match pin: {relative}')
    manifest = json.loads((runtime / 'manifest.json').read_text())
    if (manifest.get('platform'), manifest.get('arch'), manifest.get('runtime_archive_version')) != (
            'windows', 'x64', expected_runtime):
        raise ValueError('Installed Windows CUA runtime does not match pin.')
    launcher = _component(app, 'app/resources/cua_node/bin/node_modules/@oai/cua-repl/bin/cua-repl.mjs')
    return InstalledWindowsApplication(app, resources, runtime, launcher, 'windows',
                                       expected_version, 'x64')
