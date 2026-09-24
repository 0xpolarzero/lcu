#!/usr/bin/env python3
"""Build a thin LCU archive; the official app is provisioned during setup."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

sys.dont_write_bytecode = True
from bundle import VERSION, architecture, seal, verify
from provision_agent_tools import provision as provision_agents

SOURCE = Path(__file__).resolve().parents[1]


def build(output, package=None, *, target='linux', app=None):
    if package is not None:
        raise ValueError('The official app is acquired during installation. Pass --app-package to scripts/install.sh instead.')
    # The Windows archive contains only platform-neutral LCU source and locked
    # JavaScript dependencies. Build it on a trusted development host; the
    # Windows installer validates the registered official MSIX in place.
    arch = 'x64' if target == 'windows' else architecture(target)
    selected_node = None
    if target == 'darwin':
        sys.path.insert(0, str(SOURCE))
        from lcu.platforms import resolve_installed_mac_app
        policy = json.loads((SOURCE / 'runtime.lock.json').read_text())['platforms']['darwin']
        entry = policy['architectures'].get(arch)
        if entry is None:
            raise ValueError(f'No pinned macOS application for {arch}.')
        selected = resolve_installed_mac_app(
            app or Path('/Applications/ChatGPT.app'),
            expected_version=policy['version'], expected_runtime=policy['runtime'],
            expected_hashes=entry['components'], arch=arch)
        selected_node = selected.runtime / 'bin/node'
    elif target not in ('linux', 'windows') or app is not None:
        raise ValueError('An installed application path is supported only for a macOS build.')
    output.mkdir(parents=True, exist_ok=True)
    name = f'lcu-{VERSION}-{target}-{arch}'
    destination = output / (name + ('.zip' if target == 'windows' else '.tar.gz'))
    if destination.exists() or destination.with_suffix(destination.suffix + '.sha256').exists():
        raise ValueError(f'Release already exists: {destination}; use a new output directory.')
    with tempfile.TemporaryDirectory(prefix='lcu-build-') as temporary:
        scratch = Path(temporary)
        release = scratch / name
        release.mkdir()
        shutil.copytree(SOURCE / 'bin', release / 'bin',
                        ignore=(shutil.ignore_patterns('lcu-session') if target == 'windows'
                                else shutil.ignore_patterns('*.cmd')))
        (release / 'lcu').mkdir()
        modules = ('__init__.py', 'runtime.py', 'setup.py',
                         'setup_clients.py', 'codex_hooks.py', 'app_server.py', 'browser.py',
                         'native_host.py', 'claude_visibility.py')
        if target != 'windows':
            modules += ('session.py',)
        for filename in modules:
            shutil.copy2(SOURCE / 'lcu' / filename, release / 'lcu' / filename)
        if target == 'darwin':
            shutil.copy2(SOURCE / 'lcu/platforms.py', release / 'lcu/platforms.py')
        elif target == 'windows':
            shutil.copy2(SOURCE / 'lcu/windows.py', release / 'lcu/windows.py')
        (release / 'docs').mkdir()
        for filename in ('INSTALLATION.md', 'DEVELOPMENT.md', 'INSTRUCTIONS.md',
                         'VERIFICATION.md', 'PROVENANCE.md', 'PARITY-STATUS.md',
                         'STANDALONE-ADAPTATIONS.md', 'ADAPTERS.md'):
            shutil.copy2(SOURCE / 'docs' / filename, release / 'docs' / filename)
        verification = release / 'docs/verification'
        verification.mkdir()
        for record in sorted((SOURCE / 'docs/verification').glob('*.md')):
            if record.is_symlink():
                raise ValueError(f'Verification document cannot be a symlink: {record}')
            shutil.copy2(record, verification / record.name)
        (release / 'skills/lcu').mkdir(parents=True)
        shutil.copy2(SOURCE / 'skills/lcu/SKILL.md', release / 'skills/lcu/SKILL.md')
        for filename in ('README.md', 'LICENSE', 'runtime.lock.json'):
            shutil.copy2(SOURCE / filename, release / filename)
        (release / 'scripts').mkdir()
        scripts = (('bundle.py',) if target == 'windows'
                   else ('install.sh', 'install.py', 'installed_app.py', 'bundle.py'))
        for filename in scripts:
            shutil.copy2(SOURCE / 'scripts' / filename, release / 'scripts' / filename)
        if target == 'darwin':
            shutil.copy2(SOURCE / 'scripts/install_macos.py', release / 'scripts/install_macos.py')
        elif target == 'windows':
            shutil.copy2(SOURCE / 'scripts/install_windows.py', release / 'scripts/install_windows.py')
            shutil.copy2(SOURCE / 'scripts/windows_launcher.py', release / 'scripts/windows_launcher.py')
        provision_agents(release, SOURCE / 'scripts/agent-tools', target=target,
                         mac_node=selected_node, adapters_source=SOURCE / 'adapters')
        # The installer selects and validates the matching app before registration.
        imports = 'import lcu.runtime, lcu.setup, lcu.browser, lcu.codex_hooks'
        if target != 'windows':
            imports += ', lcu.session'
        subprocess.run([sys.executable, '-B', '-c', imports],
                       cwd=release, check=True, timeout=20)
        seal(release, arch, target)
        verify(release, arch, target)
        fd, temporary_archive = tempfile.mkstemp(prefix='.lcu-', suffix=destination.suffix, dir=output)
        os.close(fd)
        try:
            if target == 'windows':
                with zipfile.ZipFile(temporary_archive, 'w', compression=zipfile.ZIP_DEFLATED,
                                     compresslevel=6) as archive:
                    for path in sorted(release.rglob('*')):
                        if path.is_symlink():
                            raise ValueError(f'Windows bundle cannot contain a symlink: {path}')
                        if path.is_file():
                            archive.write(path, arcname=(Path(name) / path.relative_to(release)).as_posix())
            else:
                with tarfile.open(temporary_archive, 'w:gz', compresslevel=6) as archive:
                    archive.add(release, arcname=name)
            os.chmod(temporary_archive, 0o644)
            os.replace(temporary_archive, destination)
        finally:
            Path(temporary_archive).unlink(missing_ok=True)
    with destination.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    destination.with_suffix(destination.suffix + '.sha256').write_text(f'{digest}  {destination.name}\n')
    print(destination)
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=SOURCE / 'dist')
    parser.add_argument('--package', type=Path, help='Deprecated; use scripts/install.sh --app-package PATH')
    parser.add_argument('--platform', choices=('linux', 'darwin', 'windows'), default='linux')
    parser.add_argument('--app', type=Path, help='Pinned locally installed ChatGPT.app for a macOS build')
    args = parser.parse_args()
    try:
        if sys.version_info < (3, 12):
            raise ValueError('Python 3.12 or later is required')
        build(args.output.resolve(), args.package.resolve() if args.package else None,
              target=args.platform, app=args.app)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        sys.exit(f'LCU build: {exc}')
