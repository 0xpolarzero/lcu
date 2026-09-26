"""Validate an installed signed macOS application for the original CUA runtime."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import platform as host_platform
import plistlib
import subprocess

from .app_layout import locate_codex_tools


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
