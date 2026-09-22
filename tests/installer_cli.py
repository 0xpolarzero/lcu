"""Validate the public installation interface against an installed release."""
from pathlib import Path
import subprocess
import sys
import tempfile

source = Path(__file__).resolve().parents[1]
bundle = Path(sys.argv[1])
installer = str(bundle / 'scripts/install.sh')
with tempfile.TemporaryDirectory() as directory:
    scratch = Path(directory)
    prefix = scratch / 'uncreated'
    for args in (['--runtime-only'], ['--user', 'root', '--yes'],
                 ['--user', 'root', '--runtime-only', '--agent', 'codex'],
                 ['--user', 'root', '--agent', 'nonexistent', '--yes']):
        result = subprocess.run([installer, '--prefix', str(prefix), '--skip-system', *args], capture_output=True)
        assert result.returncode != 0, args
        assert not prefix.exists(), args
    active = Path('/opt/cual/current').resolve()
    payload = bundle / 'runtime/lib/node_modules/@oai/cua/index.js'
    before = payload.read_bytes()
    try:
        payload.write_bytes(before + b'\n// corrupted\n')
        result = subprocess.run([installer, '--prefix', '/opt/cual', '--skip-system', '--user', 'root',
                                 '--runtime-only'], capture_output=True)
        assert result.returncode != 0 and b'integrity check failed' in result.stderr
    finally:
        payload.write_bytes(before)
    assert Path('/opt/cual/current').resolve() == active
    assert (active / 'bin/cual').is_file()
    result = subprocess.run([str(source / 'scripts/install.sh'), '--prefix', str(prefix), '--skip-system',
                             '--user', 'root', '--runtime-only'], capture_output=True)
    assert result.returncode != 0 and b'release bundle' in result.stderr
    assert not prefix.exists()
print('PASS: invalid arguments and missing payload have no side effects; corrupt bundle preserves active release')
