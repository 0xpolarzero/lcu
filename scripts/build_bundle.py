#!/usr/bin/env python3
"""Build a complete architecture-specific release; downloads occur only here."""
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
from project_runtime import provision
from provision_agent_tools import provision as provision_agents

SOURCE = Path(__file__).resolve().parents[1]


def build(output, package=None):
    arch = architecture()
    output.mkdir(parents=True, exist_ok=True)
    name = f'cual-{VERSION}-linux-{arch}'
    destination = output / (name + '.tar.gz')
    if destination.exists() or destination.with_suffix(destination.suffix + '.sha256').exists():
        raise ValueError(f'Release already exists: {destination}; use a new output directory.')
    with tempfile.TemporaryDirectory(prefix='cual-build-') as temporary:
        scratch = Path(temporary)
        release = scratch / name
        release.mkdir()
        for directory in ('bin', 'cual', 'skills', 'docs', 'instructions'):
            shutil.copytree(SOURCE / directory, release / directory, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        for filename in ('README.md', 'LICENSE', 'runtime.lock.json'):
            shutil.copy2(SOURCE / filename, release / filename)
        (release / 'scripts').mkdir()
        for filename in ('install.sh', 'install.py', 'bundle.py'):
            shutil.copy2(SOURCE / 'scripts' / filename, release / 'scripts' / filename)
        provision(release, SOURCE, scratch, arch, package)
        provision_agents(release, SOURCE / 'scripts/agent-tools')
        # Test the same executable payload the installer will copy; no display needed.
        sys.path.insert(0, str(SOURCE))
        from install import validate_release
        validate_release(release)
        seal(release, arch)
        verify(release, arch)
        fd, temporary_archive = tempfile.mkstemp(prefix='.cual-', suffix='.tar.gz', dir=output)
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
    parser.add_argument('--package', type=Path, help='Cached official .deb with the pinned checksum (build-time only)')
    args = parser.parse_args()
    try:
        if sys.version_info < (3, 12):
            raise ValueError('Python 3.12 or later is required')
        build(args.output.resolve(), args.package.resolve() if args.package else None)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        sys.exit(f'Cual build: {exc}')
