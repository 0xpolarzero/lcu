"""Validate the public installation interface against an installed release."""
from pathlib import Path
import subprocess
import tempfile

source = Path(__file__).resolve().parents[1]
installer = str(source / 'scripts/install.sh')
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
    bad = scratch / 'bad.deb'
    bad.write_bytes(b'not the pinned official package')
    result = subprocess.run([installer, '--prefix', '/opt/cual', '--skip-system', '--user', 'root',
                             '--runtime-only', '--package', str(bad)], capture_output=True)
    assert result.returncode != 0 and b'checksum mismatch' in result.stderr
    assert Path('/opt/cual/current').resolve() == active
    assert (active / 'bin/cual').is_file()
print('PASS: invalid arguments have no installation side effects; corrupt package preserves active release')
