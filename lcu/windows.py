"""Validate an official Windows Store package and its intact private copy."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import xml.etree.ElementTree as ET
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
    'app/resources/cua_node/bin/node_modules/@oai/sky/dist/project/cua/sky_js/src/service.js',
    'app/resources/cua_node/bin/node_modules/@oai/sky/dist/project/cua/sky_js/src/targets/windows/internal/helper_transport.js',
    'app/resources/cua_node/bin/node_modules/@oai/sky/dist/project/cua/sky_js/src/targets/windows/internal/computer_use_client.js',
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
    runtime_version: str
    inventory: Mapping[str, object]
    inventory_digest: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _redirected(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction())


def application_inventory(app: Path) -> dict[str, dict[str, str]]:
    """Hash the selected Store package tree for managed-copy integrity checks."""
    app = Path(app)
    root = app.lstat()
    if not stat.S_ISDIR(root.st_mode) or _redirected(app):
        raise ValueError(f'Windows application directory is missing or redirected: {app}')
    inventory = {'.': {'type': 'directory'}}
    def unreadable(error):
        raise ValueError(f'Windows application tree cannot be read: {error.filename}') from error
    for parent, directories, files in os.walk(app, followlinks=False, onerror=unreadable):
        parent = Path(parent)
        for name in sorted(directories + files):
            path = parent / name
            relative = path.relative_to(app).as_posix()
            info = path.lstat()
            if _redirected(path):
                raise ValueError(f'Windows application contains a redirected path: {path}')
            if stat.S_ISDIR(info.st_mode):
                inventory[relative] = {'type': 'directory'}
            elif stat.S_ISREG(info.st_mode):
                inventory[relative] = {'type': 'file', 'sha256': _sha256(path)}
            else:
                raise ValueError(f'Windows application contains an unsupported file: {path}')
    return inventory


def inventory_sha256(inventory: Mapping[str, object]) -> str:
    encoded = json.dumps(inventory, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _appx_identity(app: Path) -> tuple[str, str, str, str]:
    if _redirected(app) or not app.is_dir():
        raise ValueError('Windows package application directory is missing or redirected.')
    manifest_path = app / 'AppxManifest.xml'
    if _redirected(manifest_path) or not manifest_path.is_file():
        raise ValueError('Windows package identity manifest is missing or redirected.')
    try:
        root = ET.parse(manifest_path).getroot()
    except (ET.ParseError, OSError) as exc:
        raise ValueError('Windows package identity manifest is invalid.') from exc
    identity = next((node for node in root.iter()
                     if node.tag.rsplit('}', 1)[-1] == 'Identity'), None)
    if identity is None:
        raise ValueError('Windows package identity is missing.')
    name, publisher = identity.get('Name'), identity.get('Publisher')
    version, architecture = identity.get('Version'), identity.get('ProcessorArchitecture')
    if (name != PACKAGE_NAME or publisher != PACKAGE_PUBLISHER or
            not isinstance(version, str) or
            not re.fullmatch(r'\d+\.\d+\.\d+\.\d+', version) or
            architecture not in ('x64', 'X64')):
        raise ValueError('Windows package identity, version, or architecture is invalid.')
    return name, publisher, version, architecture.lower()


def _registered_package():
    # Get-AppxPackage only sees packages registered for this account. Use its
    # InstallLocation rather than guessing the WindowsApps package volume.
    command = (
        "$ErrorActionPreference='Stop'; "
        "$packages=@(Get-AppxPackage -Name 'OpenAI.Codex'); "
        "$packages | Select-Object Name,Publisher,"
        "@{Name='Version';Expression={$_.Version.ToString()}},"
        "@{Name='Architecture';Expression={$_.Architecture.ToString()}},"
        "@{Name='SignatureKind';Expression={$_.SignatureKind.ToString()}},"
        'InstallLocation '
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
    if (not isinstance(packages[0].get('Version'), str) or
            not isinstance(packages[0].get('Architecture'), str) or
            not isinstance(packages[0].get('SignatureKind'), str)):
        raise ValueError('Windows package query did not return string version, architecture and signature kind.')
    return packages[0]


def _component(app: Path, relative: str) -> Path:
    expected = app / relative
    if expected.is_file():
        return expected
    # MSIX stores `@` as `%40` in its OPC archive. Accept either spelling in
    # the deployed package, but no arbitrary path fallback.
    encoded = app / relative.replace('@oai/', '%40oai/')
    return encoded if encoded.is_file() else expected


def resolve_installed_windows_app() -> InstalledWindowsApplication:
    """Select and structurally validate the current user's official Store app."""
    _validate_host()
    package = _registered_package()
    if (package.get('Name') != PACKAGE_NAME or package.get('Publisher') != PACKAGE_PUBLISHER or
            str(package.get('Architecture')).lower() not in ('x64', 'amd64') or
            package.get('SignatureKind') != 'Store'):
        raise ValueError('Registered ChatGPT package is not the official Windows x64 Store app.')
    selected = package.get('InstallLocation')
    if not isinstance(selected, str) or not selected:
        raise ValueError('Registered ChatGPT package has no install location.')
    app = Path(selected)
    _, _, version, _ = _appx_identity(app)
    if str(package.get('Version')) != version:
        raise ValueError('Registered ChatGPT package version does not match its identity manifest.')
    manifest = _runtime_manifest(app)
    runtime_version = manifest['runtime_archive_version']
    # Capture the registered source's exact tree as the baseline for its
    # managed copy. The validator recomputes it before returning the selection.
    inventory = application_inventory(app)
    return validate_windows_app_tree(app, expected_version=version,
        expected_runtime=runtime_version, expected_inventory=inventory)


def _validate_host() -> None:
    if platform.system() != 'Windows' or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise ValueError('The Windows application can only be validated on Windows x64.')


def _runtime_manifest(app: Path) -> dict:
    path = _component(app, 'app/resources/cua_node/manifest.json')
    if _redirected(path) or not path.is_file():
        raise ValueError('Windows CUA runtime manifest is missing or redirected.')
    try:
        manifest = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError('Windows CUA runtime manifest is invalid.') from exc
    if not isinstance(manifest, dict):
        raise ValueError('Windows CUA runtime manifest is invalid.')
    version = manifest.get('runtime_archive_version')
    if (manifest.get('platform') != 'windows' or manifest.get('arch') != 'x64' or
            not isinstance(version, str) or not version.strip()):
        raise ValueError('Windows CUA runtime manifest has an unsupported platform or architecture.')
    return manifest


def validate_windows_app_tree(app: Path, *, expected_version: str, expected_runtime: str,
                              expected_inventory: Mapping[str, object]) -> InstalledWindowsApplication:
    """Validate host layout and exact equality with a source-derived inventory."""
    _validate_host()
    if not expected_version or not expected_runtime or not isinstance(expected_inventory, Mapping):
        raise ValueError('A selected Windows version, runtime and source inventory are required.')
    app = Path(app)
    if _redirected(app) or not app.is_dir():
        raise ValueError('Windows application directory is missing or redirected.')
    app = app.resolve(strict=True)
    _, _, manifest_version, _ = _appx_identity(app)
    if manifest_version != expected_version:
        raise ValueError('Windows application identity version changed after selection.')
    resources = app / 'app/resources'
    runtime = resources / 'cua_node'
    for relative in WINDOWS_REQUIRED_FILES:
        file = _component(app, relative)
        if (not file.is_file() or _redirected(file) or
                any(_redirected(parent)
                    for parent in file.parents if parent != app and parent.is_relative_to(app)) or
                not file.resolve(strict=True).is_relative_to(app) or
                not file.resolve(strict=True).is_file()):
            raise ValueError(f'Required Windows application file is missing or outside the app: {relative}')
    manifest = _runtime_manifest(app)
    runtime_version = manifest['runtime_archive_version']
    if runtime_version != expected_runtime:
        raise ValueError('Windows CUA runtime changed after selection.')
    actual_inventory = application_inventory(app)
    if actual_inventory != expected_inventory:
        differing = sorted(set(actual_inventory) | set(expected_inventory))
        first = next((path for path in differing
                      if actual_inventory.get(path) != expected_inventory.get(path)), '<tree>')
        raise ValueError(f'Windows application differs from selected source inventory: {first}')
    launcher = _component(app, 'app/resources/cua_node/bin/node_modules/@oai/cua-repl/bin/cua-repl.mjs')
    return InstalledWindowsApplication(app, resources, runtime, launcher, 'windows',
                                       expected_version, 'x64', runtime_version,
                                       expected_inventory, inventory_sha256(expected_inventory))
