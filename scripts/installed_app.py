"""Select the locally installed ChatGPT Linux application in place."""
import hashlib
import os
from pathlib import Path
import subprocess
from urllib.request import Request, urlopen

from lcu.platforms import LINUX_APP_PATH, resolve_installed_linux_app
from lcu.setup import app_prerequisite_message


DEFAULT_APP_PATH = LINUX_APP_PATH


def _download(lock, entry, destination):
    """Fetch the pinned development/test package fixture; the installer never calls this."""
    url = lock['source'].format(deb_arch=entry['deb_arch'])
    request = Request(url, headers={'User-Agent': 'lcu/0.3.0'})
    digest = hashlib.sha256()
    try:
        with urlopen(request, timeout=60) as response, destination.open('xb') as output:
            while chunk := response.read(1024 * 1024):
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    if digest.hexdigest() != entry['sha256']:
        destination.unlink(missing_ok=True)
        raise ValueError('Official application package checksum mismatch; refusing to extract it')


def _run_as(command, account=None, **options):
    if account is None:
        return subprocess.run(command, **options)
    env = dict(os.environ, HOME=account.pw_dir, USER=account.pw_name, LOGNAME=account.pw_name)
    options['env'] = env
    options.setdefault('cwd', account.pw_dir)
    if os.getuid() == 0 and account.pw_uid != 0:
        options.update(user=account.pw_uid, group=account.pw_gid,
                       extra_groups=os.getgrouplist(account.pw_name, account.pw_gid))
    elif os.getuid() != account.pw_uid:
        raise ValueError(f'Cannot validate the application as {account.pw_name} from this account')
    return subprocess.run(command, **options)


def select(arch, *, existing_app=None, account=None, execute=True):
    """Validate the installed app where it is and describe the observed version and runtime."""
    existing_app = Path(existing_app).expanduser() if existing_app is not None else DEFAULT_APP_PATH
    if not existing_app.is_dir():
        raise ValueError(app_prerequisite_message(existing_app, alternate_location=True))
    selected = resolve_installed_linux_app(
        existing_app, arch=arch, trusted_uids={account.pw_uid} if account is not None else None)
    if execute:
        _run_as([str(selected.runtime / 'bin/node'), '--version'], account, check=True,
                capture_output=True, text=True, timeout=20)
        _run_as([str(selected.runtime / 'bin/node_repl'), '--help'], account, check=True,
                stdout=subprocess.DEVNULL, timeout=20)
        _run_as([str(selected.codex_cli), '--version'], account, check=True,
                capture_output=True, text=True, timeout=20)
    return selected.app, {'package_version': selected.version, 'runtime': selected.runtime_version,
                          'architecture': arch}
