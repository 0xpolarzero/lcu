"""Acquire and manage the pinned complete ChatGPT Linux application."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import stat
from urllib.request import Request, urlopen


def _sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _tree_inventory(application):
    """Return a deterministic inventory of every path in an application tree."""
    application = Path(application)
    root_info = application.lstat()
    if not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode):
        raise ValueError(f'Application tree root is not a regular directory: {application}')
    inventory = {'.': {'type': 'directory', 'mode': stat.S_IMODE(root_info.st_mode)}}
    for parent, directories, files in os.walk(application, followlinks=False):
        parent = Path(parent)
        for name in sorted(directories + files):
            path = parent / name
            relative = path.relative_to(application).as_posix()
            info = path.lstat()
            mode = stat.S_IMODE(info.st_mode)
            if stat.S_ISLNK(info.st_mode):
                inventory[relative] = {'type': 'symlink', 'mode': mode, 'target': os.readlink(path)}
                if name in directories:
                    directories.remove(name)
            elif stat.S_ISDIR(info.st_mode):
                inventory[relative] = {'type': 'directory', 'mode': mode}
            elif stat.S_ISREG(info.st_mode):
                inventory[relative] = {'type': 'file', 'mode': mode, 'sha256': _sha256(path)}
            else:
                raise ValueError(f'Unsupported special file in application tree: {path}')
    return inventory


def _package_inventory(deb, arch, lock, account=None):
    _package_identity(deb, arch, lock)
    with tempfile.TemporaryDirectory(prefix='lcu-app-baseline-') as temporary:
        payload = Path(temporary) / 'payload'
        subprocess.run(['dpkg-deb', '--extract', str(deb), str(payload)],
                       check=True, timeout=180)
        application = payload / 'usr/lib/chatgpt'
        if not application.is_dir() or application.is_symlink():
            raise ValueError('Official application package has no regular chatgpt application directory')
        return _tree_inventory(application)


def _compare_inventory(application, expected):
    actual = _tree_inventory(application)
    if actual != expected:
        differing = sorted(set(actual) | set(expected))
        first = next((path for path in differing if actual.get(path) != expected.get(path)), '<tree>')
        raise ValueError(f'Application tree does not match the verified official package: {first}')


def _lock(root):
    return json.loads((Path(root) / 'runtime.lock.json').read_text())


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


def _validate_app(application, arch, lock, package_version=None, account=None, execute=True):
    application = Path(application)
    runtime = application / 'resources/cua_node'
    manifest_path = runtime / 'manifest.json'
    if not manifest_path.is_file():
        raise ValueError(f'Pinned application runtime is missing: {manifest_path}')
    manifest = json.loads(manifest_path.read_text())
    if (manifest.get('platform'), manifest.get('arch'), manifest.get('runtime_archive_version')) != (
            'linux', arch, lock['runtime']):
        raise ValueError('Application runtime version or architecture does not match runtime.lock.json')
    required = (
        application / 'ChatGPT', runtime / 'bin/node', runtime / 'bin/node_repl',
        application / 'resources/codex', application / 'resources/codex-code-mode-host',
        application / 'resources/app.asar',
        application / 'resources/plugins/openai-bundled/plugins/browser',
        application / 'resources/plugins/openai-bundled/plugins/chrome/.codex-plugin/plugin.json',
        application / f'resources/plugins/openai-bundled/plugins/chrome/extension-host/linux/{arch}/extension-host',
        application / 'resources/plugins/openai-bundled/plugins/unified-computer-use/.mcp.json',
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise ValueError('Application payload is incomplete: ' + ', '.join(missing))
    for path in (application / 'ChatGPT', runtime / 'bin/node', runtime / 'bin/node_repl',
                 application / 'resources/codex',
                 application / f'resources/plugins/openai-bundled/plugins/chrome/extension-host/linux/{arch}/extension-host'):
        if not os.access(path, os.X_OK):
            raise ValueError(f'Application executable is not executable: {path}')
    if package_version and package_version != lock['version']:
        raise ValueError(f'Unexpected application package version: {package_version}')
    components = lock['architectures'][arch].get('components')
    if not isinstance(components, dict) or not components:
        raise ValueError('runtime.lock.json has no pinned application component hashes; --existing-app cannot be verified')
    for relative, expected in components.items():
        relative_path = Path(relative)
        if relative_path.is_absolute() or '..' in relative_path.parts:
            raise ValueError(f'Unsafe application component path in runtime.lock.json: {relative}')
        component = application / relative_path
        if not component.is_file() or component.is_symlink():
            raise ValueError(f'Pinned application component is missing or not a regular file: {component}')
        if _sha256(component) != expected:
            raise ValueError(f'Application component does not match runtime.lock.json: {relative}')
    if execute:
        _run_as([str(runtime / 'bin/node'), '--version'], account, check=True,
                capture_output=True, text=True, timeout=20)
        _run_as([str(runtime / 'bin/node_repl'), '--help'], account, check=True,
                stdout=subprocess.DEVNULL, timeout=20)
        _run_as([str(application / 'resources/codex'), '--version'], account, check=True,
                capture_output=True, text=True, timeout=20)
    return manifest


def _managed_generation(prefix, arch, lock, entry):
    return Path(prefix) / 'apps' / f"{lock['version']}-{arch}-{entry['sha256'][:16]}"


def _mark_prefix(prefix):
    prefix = Path(prefix)
    prefix.mkdir(parents=True, exist_ok=True)
    marker = prefix / '.lcu-install'
    if marker.is_symlink():
        raise ValueError(f'Refusing a symlink at {marker}')
    marker.touch(exist_ok=True)


def _validate_managed(path, arch, lock, entry, account=None, execute=True):
    if Path(path).is_symlink():
        return False
    marker = Path(path) / 'installed.json'
    if marker.is_symlink():
        return False
    try:
        data = json.loads(marker.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    expected = {'package_version': lock['version'], 'architecture': arch,
                'sha256': entry['sha256'], 'application': 'payload/usr/lib/chatgpt'}
    if any(data.get(key) != value for key, value in expected.items()):
        return False
    inventory = data.get('inventory')
    if not isinstance(inventory, dict):
        return False
    try:
        application = Path(path) / expected['application']
        _validate_app(application, arch, lock, lock['version'], account, execute)
        _compare_inventory(application, inventory)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.SubprocessError):
        return False
    return True


def _download(lock, entry, destination):
    url = lock['source'].format(deb_arch=entry['deb_arch'])
    request = Request(url, headers={'User-Agent': 'lcu/0.3.0-dev'})
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


def _cached_package(prefix, arch, lock, entry, package=None, offline=False):
    cache = Path(prefix) / 'cache'
    if cache.is_symlink():
        raise ValueError(f'Refusing a symlink at the application package cache: {cache}')
    name = f"chatgpt_{lock['version']}_{arch}_{entry['sha256'][:16]}.deb"
    destination = cache / name
    source = Path(package).resolve(strict=True) if package is not None else None
    if source is not None and _sha256(source) != entry['sha256']:
        raise ValueError('Local application package checksum mismatch')
    _mark_prefix(prefix)
    cache.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ValueError(f'Refusing a symlink in the application package cache: {destination}')
    if destination.exists() and _sha256(destination) != entry['sha256']:
        raise ValueError(f'Cached application package is corrupt: {destination}')
    if package is not None:
        if not destination.exists():
            temporary = cache / ('.' + name + '.stage')
            if temporary.is_symlink() or (temporary.exists() and not temporary.is_file()):
                raise ValueError(f'Unsafe package cache staging path: {temporary}')
            # The per-prefix install lock has been acquired by the caller.
            # A dead install can leave this task-owned staging file behind.
            temporary.unlink(missing_ok=True)
            try:
                shutil.copyfile(source, temporary)
                temporary.chmod(0o644)
                with temporary.open('rb') as stream:
                    os.fsync(stream.fileno())
                if _sha256(temporary) != entry['sha256']:
                    raise ValueError('Local application package changed while copying into the cache')
                os.replace(temporary, destination)
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
        return destination
    if destination.exists():
        return destination
    temporary = cache / ('.' + name + '.download')
    if temporary.is_symlink() or (temporary.exists() and not temporary.is_file()):
        raise ValueError(f'Unsafe package cache staging path: {temporary}')
    if temporary.exists():
        if _sha256(temporary) == entry['sha256']:
            os.replace(temporary, destination)
            return destination
        temporary.unlink()
    if offline:
        raise ValueError(f'--offline requires --app-package or a valid cached application package: {destination}')
    try:
        _download(lock, entry, temporary)
        if _sha256(temporary) != entry['sha256']:
            raise ValueError('Downloaded application package changed before cache promotion')
        temporary.chmod(0o644)
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def _package_identity(package, arch, lock):
    result = subprocess.run(['dpkg-deb', '-f', str(package), 'Package', 'Version', 'Architecture'],
                            check=True, capture_output=True, text=True, timeout=30)
    _check_package_identity(result.stdout, arch, lock)


def _check_package_identity(output, arch, lock):
    fields = {}
    for line in output.splitlines():
        name, separator, value = line.partition(':')
        if separator:
            fields[name.strip()] = value.strip()
    expected_arch = 'arm64' if arch == 'arm64' else 'amd64'
    expected = {'Package': 'chatgpt', 'Version': lock['version'], 'Architecture': expected_arch}
    if fields != expected:
        raise ValueError(f'Unexpected official package identity: {fields!r}')


def preflight(prefix, arch, *, package=None, existing_app=None, offline=False, root=None, account=None):
    """Resolve and authenticate the acquisition source before system changes."""
    if package is not None and existing_app is not None:
        raise ValueError('Choose only one of --app-package and --existing-app')
    root = Path(root) if root else Path(__file__).resolve().parents[1]
    lock = _lock(root)
    entry = lock['architectures'][arch]
    if package is not None and _sha256(Path(package).resolve(strict=True)) != entry['sha256']:
        raise ValueError('Local application package checksum mismatch')
    generation = _managed_generation(prefix, arch, lock, entry)
    prefix = Path(prefix)
    prefix.mkdir(parents=True, exist_ok=True)
    _mark_prefix(prefix)
    with (prefix / '.lcu-install').open('a') as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        if generation.exists() or generation.is_symlink():
            if not _validate_managed(generation, arch, lock, entry, account, execute=False):
                raise ValueError(f'Existing managed application is incomplete or corrupt: {generation}')
            return
        if existing_app is not None:
            deb = _cached_package(prefix, arch, lock, entry, offline=offline)
            baseline = _package_inventory(deb, arch, lock, account)
            application = Path(existing_app).resolve(strict=True)
            _validate_app(application, arch, lock, lock['version'], account, execute=False)
            _compare_inventory(application, baseline)
            return
        deb = _cached_package(prefix, arch, lock, entry, package=package, offline=offline)
        _package_identity(deb, arch, lock)


def provision(prefix, arch, *, package=None, existing_app=None, offline=False, root=None, account=None):
    """Return the selected full application and its managed application directory."""
    prefix = Path(prefix)
    root = Path(root) if root else Path(__file__).resolve().parents[1]
    lock = _lock(root)
    try:
        entry = lock['architectures'][arch]
    except KeyError as exc:
        raise ValueError(f'No pinned application for architecture: {arch}') from exc
    if package is not None and existing_app is not None:
        raise ValueError('Choose only one of --app-package and --existing-app')
    generation = _managed_generation(prefix, arch, lock, entry)
    _mark_prefix(prefix)
    apps = prefix / 'apps'
    if apps.is_symlink():
        raise ValueError(f'Refusing a symlink at the managed application directory: {apps}')
    with (prefix / '.lcu-install').open('a') as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        apps.mkdir(parents=True, exist_ok=True)
        if _validate_managed(generation, arch, lock, entry, account):
            return generation / 'payload/usr/lib/chatgpt', generation
        if generation.exists():
            raise ValueError(f'Existing managed application is incomplete or corrupt: {generation}')
        if generation.is_symlink():
            raise ValueError(f'Refusing a symlink at the managed application generation: {generation}')
        if offline and package is None and existing_app is None:
            cache_package = _cached_package(prefix, arch, lock, entry, offline=True)
        else:
            cache_package = None
        stage = Path(tempfile.mkdtemp(prefix='.app-stage-', dir=apps))
        try:
            payload = stage / 'payload'
            application = payload / 'usr/lib/chatgpt'
            if existing_app is not None:
                deb = _cached_package(prefix, arch, lock, entry, offline=offline)
                inventory = _package_inventory(deb, arch, lock, account)
            else:
                deb = cache_package or _cached_package(prefix, arch, lock, entry,
                                                       package=package, offline=offline)
                inventory = _package_inventory(deb, arch, lock, account)
            if existing_app is not None:
                source_app = Path(existing_app).resolve(strict=True)
                _validate_app(source_app, arch, lock, lock['version'], account)
                _compare_inventory(source_app, inventory)
                application.parent.mkdir(parents=True)
                shutil.copytree(source_app, application, symlinks=True)
                stage.chmod(0o755)
                _validate_app(application, arch, lock, lock['version'], account)
                _compare_inventory(application, inventory)
            else:
                payload.mkdir()
                subprocess.run(['dpkg-deb', '--extract', str(deb), str(payload)], check=True, timeout=180)
                # The selected desktop account must traverse the staging root
                # while validating the just-extracted native runtime.
                stage.chmod(0o755)
                _validate_app(application, arch, lock, lock['version'], account)
                _compare_inventory(application, inventory)
            (stage / 'installed.json').write_text(json.dumps({
                'package_version': lock['version'], 'architecture': arch,
                'sha256': entry['sha256'], 'application': 'payload/usr/lib/chatgpt',
                'source': 'existing-app' if existing_app is not None else 'official-package',
                'inventory': inventory,
            }, indent=2) + '\n')
            (stage / 'installed.json').chmod(0o644)
            os.replace(stage, generation)
        except BaseException:
            shutil.rmtree(stage, ignore_errors=True)
            raise
    return generation / 'payload/usr/lib/chatgpt', generation
