"""Acquire and manage a compatible complete ChatGPT Linux application."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import stat
from urllib.request import Request, urlopen

from lcu.app_layout import locate_codex_tools
from lcu.asar import read_asar_members


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


def _inventory_digest(inventory):
    encoded = json.dumps(inventory, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(encoded).hexdigest()


def _package_inventory(deb, arch, lock=None, account=None):
    package_version = _package_identity(deb, arch, lock)
    with tempfile.TemporaryDirectory(prefix='lcu-app-baseline-') as temporary:
        payload = Path(temporary) / 'payload'
        subprocess.run(['dpkg-deb', '--extract', str(deb), str(payload)],
                       check=True, timeout=180)
        application = payload / 'usr/lib/chatgpt'
        if not application.is_dir() or application.is_symlink():
            raise ValueError('Application package has no regular chatgpt application directory')
        manifest = _validate_app(application, arch, account=account, execute=False)
        return package_version, manifest, _tree_inventory(application)


def _select(prefix, arch, lock, entry, *, package=None, existing_app=None,
            offline=False, account=None, execute=False):
    if package is not None and existing_app is not None:
        raise ValueError('Choose only one of --app-package and --existing-app')
    if existing_app is not None:
        source_app = Path(existing_app).resolve(strict=True)
        manifest = _validate_app(source_app, arch, account=account, execute=execute)
        package_version = _application_version(source_app, arch)
        inventory = _tree_inventory(source_app)
        deb = None
        source = 'existing-app'
        package_sha256 = None
        managed_valid = False
    else:
        if package is None and entry is None:
            raise ValueError(f'No official application package is pinned for architecture: {arch}')
        deb = _cached_package(prefix, arch, lock, entry, package=package, offline=offline)
        package_lock = lock if package is None else None
        package_version = _package_identity(deb, arch, package_lock)
        package_sha256 = _sha256(deb)
        reused = _find_managed_package(prefix, arch, lock, deb, package_version, account, execute)
        if reused is not None:
            return reused
        package_version, manifest, inventory = _package_inventory(
            deb, arch, package_lock, account)
        source_app = None
        source = 'official-package' if package is None else 'local-package'
        managed_valid = False
    descriptor = {
        'package_version': package_version,
        'runtime': manifest['runtime_archive_version'],
        'architecture': arch,
        'sha256': _inventory_digest(inventory),
        'application': 'payload/usr/lib/chatgpt',
    }
    tree_entry = {'sha256': descriptor['sha256']}
    return {'descriptor': descriptor, 'entry': tree_entry, 'inventory': inventory,
            'generation': _managed_generation(prefix, arch, lock, tree_entry, package_version),
            'source_app': source_app, 'deb': deb, 'source': source,
            'package_sha256': package_sha256, 'managed_valid': managed_valid}


def _compare_inventory(application, expected):
    actual = _tree_inventory(application)
    if actual != expected:
        differing = sorted(set(actual) | set(expected))
        first = next((path for path in differing if actual.get(path) != expected.get(path)), '<tree>')
        raise ValueError(f'Application tree changed after selection: {first}')


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


def _validate_app(application, arch, account=None, execute=True):
    application = Path(application)
    resources = application / 'resources'
    runtime = application / 'resources/cua_node'
    manifest_path = runtime / 'manifest.json'
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError(f'Application runtime manifest is missing: {manifest_path}')
    manifest = json.loads(manifest_path.read_text())
    runtime_version = manifest.get('runtime_archive_version')
    if (manifest.get('platform') != 'linux' or manifest.get('arch') != arch or
            not isinstance(runtime_version, str) or not runtime_version.strip()):
        raise ValueError('Application runtime manifest has an unsupported platform, architecture, or version')
    tools = locate_codex_tools(resources)
    required = (
        application / 'ChatGPT', runtime / 'bin/node', runtime / 'bin/node_repl',
        runtime / 'lib/node_modules/@oai/cua-repl/bin/cua-repl.mjs',
        tools.cli, tools.code_mode_host, resources / 'app.asar',
        resources / 'plugins/openai-bundled/plugins/chrome/.codex-plugin/plugin.json',
        resources / f'plugins/openai-bundled/plugins/chrome/extension-host/linux/{arch}/extension-host',
        resources / 'plugins/openai-bundled/plugins/unified-computer-use/.mcp.json',
    )
    missing = [str(path) for path in required if path.is_symlink() or not path.is_file()]
    browser_plugin = resources / 'plugins/openai-bundled/plugins/browser'
    if browser_plugin.is_symlink() or not browser_plugin.is_dir():
        missing.append(str(browser_plugin))
    if missing:
        raise ValueError('Application payload is incomplete: ' + ', '.join(missing))
    for path in (application / 'ChatGPT', runtime / 'bin/node', runtime / 'bin/node_repl',
                 tools.cli,
                 resources / f'plugins/openai-bundled/plugins/chrome/extension-host/linux/{arch}/extension-host'):
        if not os.access(path, os.X_OK):
            raise ValueError(f'Application executable is not executable: {path}')
    if execute:
        _run_as([str(runtime / 'bin/node'), '--version'], account, check=True,
                capture_output=True, text=True, timeout=20)
        _run_as([str(runtime / 'bin/node_repl'), '--help'], account, check=True,
                stdout=subprocess.DEVNULL, timeout=20)
        _run_as([str(tools.cli), '--version'], account, check=True,
                capture_output=True, text=True, timeout=20)
    return manifest


def _managed_generation(prefix, arch, lock, entry, package_version=None):
    version = package_version or lock['version']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.+:~_-]*', version):
        raise ValueError('ChatGPT package version contains unsafe path characters')
    return Path(prefix) / 'apps' / f'{version}-{arch}-{entry["sha256"][:16]}'


def _mark_prefix(prefix):
    prefix = Path(prefix)
    prefix.mkdir(parents=True, exist_ok=True)
    marker = prefix / '.lcu-install'
    if marker.is_symlink():
        raise ValueError(f'Refusing a symlink at {marker}')
    marker.touch(exist_ok=True)


def _validate_managed(path, arch, lock, entry, account=None, execute=True,
                      package_version=None, runtime=None, package_sha256=None):
    if Path(path).is_symlink():
        return False
    marker = Path(path) / 'installed.json'
    if marker.is_symlink():
        return False
    try:
        data = json.loads(marker.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    expected = {'package_version': package_version or lock['version'], 'architecture': arch,
                'sha256': entry['sha256'], 'application': 'payload/usr/lib/chatgpt'}
    if runtime is not None:
        expected['runtime'] = runtime
    if package_sha256 is not None:
        expected['package_sha256'] = package_sha256
    if any(data.get(key) != value for key, value in expected.items()):
        return False
    inventory = data.get('inventory')
    if not isinstance(inventory, dict) or _inventory_digest(inventory) != entry['sha256']:
        return False
    try:
        application = Path(path) / expected['application']
        manifest = _validate_app(application, arch, account, execute)
        if runtime is not None and manifest['runtime_archive_version'] != runtime:
            return False
        _compare_inventory(application, inventory)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.SubprocessError):
        return False
    return True


def _find_managed_package(prefix, arch, lock, deb, package_version, account=None, execute=False):
    """Reuse a generation created from the same package bytes without re-extracting it."""
    package_sha = _sha256(deb)
    apps = Path(prefix) / 'apps'
    if apps.is_symlink() or not apps.is_dir():
        return None
    for generation in sorted(apps.glob(f'{package_version}-{arch}-*')):
        marker = generation / 'installed.json'
        if generation.is_symlink() or marker.is_symlink() or not marker.is_file():
            continue
        try:
            data = json.loads(marker.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if (data.get('package_version') != package_version or
                data.get('architecture') != arch or data.get('package_sha256') != package_sha):
            continue
        descriptor = {key: data.get(key) for key in
                      ('package_version', 'runtime', 'architecture', 'sha256', 'application')}
        if (not isinstance(descriptor['runtime'], str) or not descriptor['runtime'] or
                not isinstance(descriptor['sha256'], str) or
                not re.fullmatch(r'[0-9a-f]{64}', descriptor['sha256']) or
                generation != _managed_generation(prefix, arch, lock,
                                                   {'sha256': descriptor['sha256']}, package_version)):
            raise ValueError(f'Existing managed application has an invalid identity: {generation}')
        if not _validate_managed(generation, arch, lock, {'sha256': descriptor['sha256']},
                                 account, execute, package_version, descriptor['runtime'], package_sha):
            raise ValueError(f'Existing managed application is incomplete or corrupt: {generation}')
        return {'descriptor': descriptor, 'inventory': data['inventory'],
                'entry': {'sha256': descriptor['sha256']}, 'generation': generation,
                'source_app': None, 'deb': deb, 'source': data.get('source', 'official-package'),
                'package_sha256': package_sha, 'managed_valid': True}
    return None


def _download(lock, entry, destination):
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


def _cached_package(prefix, arch, lock, entry, package=None, offline=False):
    cache = Path(prefix) / 'cache'
    if cache.is_symlink():
        raise ValueError(f'Refusing a symlink at the application package cache: {cache}')
    source = Path(package).resolve(strict=True) if package is not None else None
    if source is not None:
        package_version = _package_identity(source, arch)
        package_sha = _sha256(source)
    else:
        if entry is None:
            raise ValueError(f'No official application package is pinned for architecture: {arch}')
        package_version = lock['version']
        package_sha = entry['sha256']
    name = f'chatgpt_{package_version}_{arch}_{package_sha[:16]}.deb'
    destination = cache / name
    _mark_prefix(prefix)
    cache.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ValueError(f'Refusing a symlink in the application package cache: {destination}')
    if destination.exists() and _sha256(destination) != package_sha:
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
                if (_sha256(temporary) != package_sha or
                        _package_identity(temporary, arch) != package_version):
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
        if _sha256(temporary) == package_sha:
            _package_identity(temporary, arch, lock)
            os.replace(temporary, destination)
            return destination
        temporary.unlink()
    if offline:
        raise ValueError(f'--offline requires --app-package or a valid cached application package: {destination}')
    try:
        _download(lock, entry, temporary)
        if _sha256(temporary) != package_sha:
            raise ValueError('Downloaded application package changed before cache promotion')
        _package_identity(temporary, arch, lock)
        temporary.chmod(0o644)
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def _package_identity(package, arch, lock=None):
    result = subprocess.run(['dpkg-deb', '-f', str(package), 'Package', 'Version', 'Architecture'],
                            check=True, capture_output=True, text=True, timeout=30)
    return _check_package_identity(result.stdout, arch, lock)


def _check_package_identity(output, arch, lock=None):
    fields = {}
    for line in output.splitlines():
        name, separator, value = line.partition(':')
        if separator:
            fields[name.strip()] = value.strip()
    expected_arch = 'arm64' if arch == 'arm64' else 'amd64'
    version = fields.get('Version')
    if (fields.get('Package') != 'chatgpt' or fields.get('Architecture') != expected_arch or
            not version or (lock is not None and version != lock['version'])):
        raise ValueError(f'Unexpected ChatGPT package identity: {fields!r}')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.+:~_-]*', version):
        raise ValueError('ChatGPT package version contains unsafe path characters')
    return version


def _application_version(application, arch):
    """Read the selected app version or verify that dpkg owns its exact path."""
    application = Path(application)
    try:
        package = json.loads(read_asar_members(
            application / 'resources/app.asar', ('package.json',))['package.json'])
        version = package.get('version')
        if isinstance(version, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.+:~_-]*', version):
            return version
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        pass

    executable = application / 'ChatGPT'
    try:
        ownership = subprocess.run(['dpkg-query', '-S', '--', str(executable)],
                                   check=True, capture_output=True, text=True, timeout=20)
        owners = []
        for line in ownership.stdout.splitlines():
            owner, separator, path = line.partition(': ')
            if (separator and Path(path) == executable and
                    owner.split(':', 1)[0] == 'chatgpt'):
                owners.append(owner)
        if len(owners) != 1:
            raise ValueError('No unique chatgpt package owns the selected executable path')
        result = subprocess.run(['dpkg-query', '-W', '--showformat=%v %a', owners[0]],
                                check=True, capture_output=True, text=True, timeout=20)
        fields = result.stdout.split()
        expected_arch = 'arm64' if arch == 'arm64' else 'amd64'
        if len(fields) != 2 or fields[1] != expected_arch:
            raise ValueError('The selected dpkg-owned ChatGPT path has the wrong architecture')
        if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.+:~_-]*', fields[0]):
            return fields[0]
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError('Cannot determine the selected app version from app.asar or its dpkg-owned path') from exc
    raise ValueError('Cannot determine the selected app version from app.asar or its dpkg-owned path')


def preflight(prefix, arch, *, package=None, existing_app=None, offline=False, root=None, account=None):
    """Resolve and structurally validate the acquisition source before system changes."""
    root = Path(root) if root else Path(__file__).resolve().parents[1]
    lock = _lock(root)
    entry = lock.get('architectures', {}).get(arch)
    prefix = Path(prefix)
    prefix.mkdir(parents=True, exist_ok=True)
    _mark_prefix(prefix)
    with (prefix / '.lcu-install').open('a') as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        selected = _select(prefix, arch, lock, entry, package=package,
                           existing_app=existing_app, offline=offline,
                           account=account, execute=False)
        descriptor = selected['descriptor']
        generation = selected['generation']
        if generation.exists() or generation.is_symlink():
            if not selected['managed_valid'] and not _validate_managed(generation, arch, lock, selected['entry'], account=account,
                                     execute=False, package_version=descriptor['package_version'],
                                     runtime=descriptor['runtime']):
                raise ValueError(f'Existing managed application is incomplete or corrupt: {generation}')


def provision(prefix, arch, *, package=None, existing_app=None, offline=False, root=None, account=None):
    """Return the selected full application and its managed application directory."""
    prefix = Path(prefix)
    root = Path(root) if root else Path(__file__).resolve().parents[1]
    lock = _lock(root)
    entry = lock.get('architectures', {}).get(arch)
    _mark_prefix(prefix)
    apps = prefix / 'apps'
    if apps.is_symlink():
        raise ValueError(f'Refusing a symlink at the managed application directory: {apps}')
    with (prefix / '.lcu-install').open('a') as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        apps.mkdir(parents=True, exist_ok=True)
        selected = _select(prefix, arch, lock, entry, package=package,
                           existing_app=existing_app, offline=offline, account=account)
        descriptor = selected['descriptor']
        generation = selected['generation']
        if selected['managed_valid']:
            return generation / descriptor['application'], generation
        if _validate_managed(generation, arch, lock, selected['entry'], account=account,
                             package_version=descriptor['package_version'], runtime=descriptor['runtime']):
            return generation / descriptor['application'], generation
        if generation.exists():
            raise ValueError(f'Existing managed application is incomplete or corrupt: {generation}')
        if generation.is_symlink():
            raise ValueError(f'Refusing a symlink at the managed application generation: {generation}')
        stage = Path(tempfile.mkdtemp(prefix='.app-stage-', dir=apps))
        try:
            payload = stage / 'payload'
            application = payload / 'usr/lib/chatgpt'
            inventory = selected['inventory']
            if selected['source_app'] is not None:
                application.parent.mkdir(parents=True)
                shutil.copytree(selected['source_app'], application, symlinks=True)
            else:
                payload.mkdir()
                subprocess.run(['dpkg-deb', '--extract', str(selected['deb']), str(payload)],
                               check=True, timeout=180)
            # The selected desktop account must traverse the staging root while
            # validating the just-extracted native runtime.
            stage.chmod(0o755)
            manifest = _validate_app(application, arch, account=account)
            if manifest['runtime_archive_version'] != descriptor['runtime']:
                raise ValueError('Application runtime changed between validation and installation')
            _compare_inventory(application, inventory)
            installed = {**descriptor, 'source': selected['source'],
                         'package_sha256': selected['package_sha256'], 'inventory': inventory}
            marker = stage / 'installed.json'
            marker.write_text(json.dumps(installed, indent=2) + '\n')
            marker.chmod(0o644)
            os.replace(stage, generation)
        except BaseException:
            shutil.rmtree(stage, ignore_errors=True)
            raise
    return generation / descriptor['application'], generation
