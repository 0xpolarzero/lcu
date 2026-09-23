#!/usr/bin/env python3
"""Install private, integrity-pinned upstream agent installers in a new release."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile
from urllib.request import urlopen

NODE_VERSION = '24.21.0'
# Official https://nodejs.org/dist/v24.21.0/SHASUMS256.txt
NODE_SHA256 = {
    'arm64': '6ad1325edbdb5649c379b75a237147a666c95d4f9ae8d340fef2d1575d289ad2',
    'x64': 'fd8e59d5a511510f6a298afb548f18c7d2b1be404d8b4a27d94fbe49f56cb2d6',
}


def download(url, destination, expected):
    digest = hashlib.sha256()
    with urlopen(url, timeout=30) as response, destination.open('xb') as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ValueError('Node download integrity check failed; refusing to execute it.')


def provision(release, source):
    architecture = {'aarch64': 'arm64', 'arm64': 'arm64', 'x86_64': 'x64', 'amd64': 'x64'}.get(platform.machine())
    if platform.system() != 'Linux' or architecture is None:
        raise ValueError('Agent installer runtime requires Linux arm64 or x64.')
    destination = release / 'agent-tools'
    destination.mkdir()
    # Keep download/cache off /tmp (often a small tmpfs in VM images).
    try:
        with tempfile.TemporaryDirectory(prefix='.agent-tools-', dir=release) as temporary:
            scratch = Path(temporary)
            name = f'node-v{NODE_VERSION}-linux-{architecture}'
            archive = scratch / 'node.tar.xz'
            download(f'https://nodejs.org/dist/v{NODE_VERSION}/{name}.tar.xz', archive, NODE_SHA256[architecture])
            with tarfile.open(archive, 'r:xz') as bundle:
                bundle.extractall(scratch, filter='data')
            (scratch / name).rename(destination / 'node')
            for filename in ('package.json', 'package-lock.json'):
                shutil.copyfile(source / filename, destination / filename)
            node = destination / 'node/bin/node'
            npm = destination / 'node/lib/node_modules/npm/bin/npm-cli.js'
            # Do not read caller npmrc, use their cache, or install globally.
            environment = {
                'PATH': str(node.parent) + ':/usr/bin:/bin',
                'HOME': str(scratch), 'LANG': 'C.UTF-8',
                'NPM_CONFIG_USERCONFIG': str(scratch / 'empty.npmrc'),
                'NPM_CONFIG_GLOBALCONFIG': str(scratch / 'global.npmrc'),
                'NPM_CONFIG_UPDATE_NOTIFIER': 'false',
            }
            subprocess.run([str(node), str(npm), 'ci', '--prefix', str(destination),
                            '--cache', str(scratch / 'npm-cache'), '--ignore-scripts',
                            '--no-audit', '--no-fund', '--registry=https://registry.npmjs.org'],
                           cwd=scratch, env=environment, check=True, timeout=180)
            expected = json.loads((destination / 'package.json').read_text())['dependencies']
            for package, entry in (('skills', 'bin/cli.mjs'), ('add-mcp', 'dist/index.js')):
                metadata = json.loads((destination / 'node_modules' / package / 'package.json').read_text())
                if metadata['version'] != expected[package]:
                    raise ValueError(f'Unexpected installed {package} version.')
                subprocess.run([str(node), str(destination / 'node_modules' / package / entry), '--version'],
                               cwd=scratch, env=environment, check=True, timeout=20)
            # Registration uses the official CUA Node selected at install time.
            # npm is only a build dependency; keep no second Node distribution.
            shutil.rmtree(destination / 'node')
            (destination / 'node/bin').mkdir(parents=True)
            (destination / 'node/bin/node').symlink_to('../../../app/resources/cua_node/bin/node')
    except BaseException:
        shutil.rmtree(destination)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parent / 'agent-tools')
    arguments = parser.parse_args()
    provision(arguments.release.resolve(), arguments.source.resolve())
