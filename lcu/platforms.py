"""Validate an installed macOS application for use by the original CUA runtime.

Linux keeps its existing managed-package validator. Windows has no inspected
application package yet, so neither platform is inferred from shared JS files.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import platform as host_platform
import plistlib
import subprocess
from typing import Mapping


MAC_BUNDLE_ID = 'com.openai.codex'
MAC_HELPER_ID = 'com.openai.sky.CUAService'
OPENAI_TEAM_ID = '2DC432GLL2'
MAC_HELPER = Path('Resources/cua_node/lib/node_modules/@oai/sky/Codex Computer Use.app')
MAC_REQUIRED_FILES = (
    'Resources/cua_node/bin/node',
    'Resources/cua_node/bin/node_repl',
    'Resources/cua_node/lib/node_modules/@oai/cua-repl/bin/cua-repl.mjs',
    'Resources/codex',
    'Resources/codex-code-mode-host',
    'Resources/plugins/openai-bundled/plugins/unified-computer-use/.mcp.json',
    'Resources/plugins/openai-bundled/plugins/chrome/.codex-plugin/plugin.json',
)
MAC_EXECUTABLES = (
    'Resources/cua_node/bin/node',
    'Resources/cua_node/bin/node_repl',
    'Resources/codex',
    'Resources/codex-code-mode-host',
)


@dataclass(frozen=True)
class InstalledApplication:
    app: Path
    resources: Path
    runtime: Path
    backend: str
    version: str
    arch: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _identity(bundle: Path, identifier: str, version: str | None = None) -> None:
    info = bundle / 'Contents/Info.plist'
    if not info.is_file() or info.is_symlink():
        raise ValueError(f'Application bundle metadata is missing: {info}')
    with info.open('rb') as source:
        details = plistlib.load(source)
    if details.get('CFBundleIdentifier') != identifier:
        raise ValueError(f'Unexpected application bundle identifier: {bundle}')
    if version is not None and details.get('CFBundleShortVersionString') != version:
        raise ValueError(f'Installed application version does not match pin: {bundle}')


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


def resolve_installed_mac_app(app_path: Path, *, expected_version: str,
                              expected_runtime: str, expected_hashes: Mapping[str, str],
                              arch: str | None = None) -> InstalledApplication:
    """Validate a pinned, local ChatGPT.app without relocating signed files.

    ``expected_hashes`` must cover every runtime entry that LCU will execute or
    use as its MCP policy. The caller owns the trusted, versioned pin source.
    """
    if host_platform.system() != 'Darwin':
        raise ValueError('The macOS application can only be validated on macOS')
    app = Path(app_path).expanduser()
    if app.is_symlink() or not app.is_dir() or app.name != 'ChatGPT.app':
        raise ValueError(f'Expected a local ChatGPT.app directory: {app}')
    app = app.resolve(strict=True)
    architecture = arch or {'arm64': 'arm64', 'aarch64': 'arm64', 'x86_64': 'x64'}.get(host_platform.machine())
    if architecture not in ('arm64', 'x64'):
        raise ValueError(f'Unsupported macOS architecture: {architecture}')
    if not expected_version or not expected_runtime:
        raise ValueError('A pinned application version and runtime are required')
    if set(expected_hashes) != set(MAC_REQUIRED_FILES):
        raise ValueError('Mac application pins must cover every required runtime file')
    if any(len(value) != 64 or any(char not in '0123456789abcdef' for char in value)
           for value in expected_hashes.values()):
        raise ValueError('Mac application pins must contain SHA-256 hex digests')

    contents = app / 'Contents'
    resources = contents / 'Resources'
    runtime = resources / 'cua_node'
    _identity(app, MAC_BUNDLE_ID, expected_version)
    helper = contents / MAC_HELPER
    _identity(helper, MAC_HELPER_ID)
    manifest_path = runtime / 'manifest.json'
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError('Installed application CUA manifest is missing')
    manifest = json.loads(manifest_path.read_text())
    if (manifest.get('platform'), manifest.get('arch'), manifest.get('runtime_archive_version')) != (
            'darwin', architecture, expected_runtime):
        raise ValueError('Installed application CUA runtime does not match pin')
    for relative in MAC_REQUIRED_FILES:
        file = contents / relative
        if not file.is_file() or file.is_symlink() or _sha256(file) != expected_hashes[relative]:
            raise ValueError(f'Installed application file does not match pin: {relative}')
        if relative in MAC_EXECUTABLES and not os.access(file, os.X_OK):
            raise ValueError(f'Installed application executable is not executable: {relative}')
    _verify_signature(app, MAC_BUNDLE_ID)
    _verify_signature(helper, MAC_HELPER_ID)
    return InstalledApplication(app, resources, runtime, 'mac', expected_version, architecture)
