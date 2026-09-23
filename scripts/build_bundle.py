#!/usr/bin/env python3
"""Build a thin LCU archive; the official app is provisioned during setup."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

sys.dont_write_bytecode = True
from bundle import VERSION, architecture, seal, verify
from provision_agent_tools import provision as provision_agents

SOURCE = Path(__file__).resolve().parents[1]


def build(output, package=None):
    if package is not None:
        raise ValueError('The official app is acquired during installation. Pass --app-package to scripts/install.sh instead.')
    arch = architecture()
    output.mkdir(parents=True, exist_ok=True)
    name = f'lcu-{VERSION}-linux-{arch}'
    destination = output / (name + '.tar.gz')
    if destination.exists() or destination.with_suffix(destination.suffix + '.sha256').exists():
        raise ValueError(f'Release already exists: {destination}; use a new output directory.')
    with tempfile.TemporaryDirectory(prefix='lcu-build-') as temporary:
        scratch = Path(temporary)
        release = scratch / name
        release.mkdir()
        shutil.copytree(SOURCE / 'bin', release / 'bin')
        (release / 'lcu').mkdir()
        for filename in ('__init__.py', 'runtime.py', 'session.py', 'setup.py',
                         'setup_clients.py', 'codex_hooks.py', 'app_server.py', 'browser.py',
                         'native_host.py'):
            shutil.copy2(SOURCE / 'lcu' / filename, release / 'lcu' / filename)
        (release / 'docs').mkdir()
        for filename in ('INSTALLATION.md', 'DEVELOPMENT.md', 'INSTRUCTIONS.md',
                         'VERIFICATION.md', 'PROVENANCE.md', 'PARITY-STATUS.md',
                         'STANDALONE-ADAPTATIONS.md'):
            shutil.copy2(SOURCE / 'docs' / filename, release / 'docs' / filename)
        (release / 'skills/lcu').mkdir(parents=True)
        shutil.copy2(SOURCE / 'skills/lcu/SKILL.md', release / 'skills/lcu/SKILL.md')
        for filename in ('README.md', 'LICENSE', 'runtime.lock.json'):
            shutil.copy2(SOURCE / filename, release / filename)
        (release / 'scripts').mkdir()
        for filename in ('install.sh', 'install.py', 'installed_app.py', 'bundle.py'):
            shutil.copy2(SOURCE / 'scripts' / filename, release / 'scripts' / filename)
        provision_agents(release, SOURCE / 'scripts/agent-tools')
        # The installer selects and validates the matching app before registration.
        subprocess.run([sys.executable, '-B', '-c',
                        'import lcu.runtime, lcu.session, lcu.setup, lcu.browser, lcu.codex_hooks'],
                       cwd=release, check=True, timeout=20)
        seal(release, arch)
        verify(release, arch)
        fd, temporary_archive = tempfile.mkstemp(prefix='.lcu-', suffix='.tar.gz', dir=output)
        os.close(fd)
        try:
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
    args = parser.parse_args()
    try:
        if sys.version_info < (3, 12):
            raise ValueError('Python 3.12 or later is required')
        build(args.output.resolve(), args.package.resolve() if args.package else None)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        sys.exit(f'LCU build: {exc}')
