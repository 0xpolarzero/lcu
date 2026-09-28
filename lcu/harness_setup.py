"""Local harness packages; host configuration remains with native installers."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def _run(argv, *, cwd, env):
    result = subprocess.run(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                            capture_output=True, text=True, encoding='utf-8',
                            errors='replace', timeout=120)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise ValueError(f'installer exited {result.returncode}' + (f': {detail}' if detail else ''))


@contextmanager
def _package(destination, harness, files, skill):
    """Replace only our own generated tree and restore it if registration fails."""
    from .setup import regular_path
    destination = regular_path(destination)
    marker = '.lcu-generated.json'
    identity = {'harness': harness}
    if destination.exists():
        manifest = regular_path(destination / marker)
        if not manifest.is_file() or json.loads(manifest.read_text()) != identity:
            raise ValueError(f'Refusing to replace an unowned plugin directory: {destination}')
        for entry in destination.rglob('*'):
            regular_path(entry)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.lcu-plugin-', dir=destination.parent) as temporary:
        stage = Path(temporary) / 'next'
        stage.mkdir()
        for relative, content in files.items():
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        # The source is the locally generated full skill, never the bootstrap
        # from the release. No original documents enter the repository/archive.
        regular_path(skill)
        for entry in skill.rglob('*'):
            regular_path(entry)
        shutil.copytree(skill, stage / 'skills/lcu')
        (stage / marker).write_text(json.dumps(identity) + '\n')
        previous = Path(temporary) / 'previous'
        if destination.exists():
            os.replace(destination, previous)
        try:
            os.replace(stage, destination)
            yield destination
        except BaseException:
            if destination.exists():
                shutil.rmtree(destination)
            if previous.exists():
                os.replace(previous, destination)
            raise


def configure_omp(home, skill, command, release, *, scope, project, env):
    if scope != 'user':
        raise ValueError('Oh My Pi native plugin links are profile-scoped. Use --scope user with the intended OMP profile; project scope is not supported.')
    executable = shutil.which('omp', path=env.get('PATH'))
    if not executable:
        raise ValueError('Oh My Pi is not on the target account PATH. Install OMP, then rerun `lcu setup --agent omp`.')
    adapter = release / 'adapters/pi/index.ts'
    if not adapter.is_file():
        raise ValueError(f'LCU Pi/OMP adapter missing: {adapter}')
    # Separate package trees prevent profile setup from changing another
    # registration's selected runtime command or Chrome instruction opt-in.
    identity = [scope, str(project.resolve()) if project else '',
                *(env.get(key, '') for key in ('OMP_PROFILE', 'PI_PROFILE', 'PI_CODING_AGENT_DIR'))]
    suffix = hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:16]
    data = home / ('AppData/Local/LCU' if os.name == 'nt' else '.local/share/lcu')
    destination = data / 'omp' / f'{scope}-{suffix}'
    manifest = {'name': 'lcu-computer-use', 'version': '0.1.0', 'private': True,
                'type': 'module', 'omp': {'extensions': ['./index.ts']}}
    # OMP's compiled loader walks relative imports to resolve transitive npm
    # dependencies. A file:// import bypasses that graph in OMP 18.1.6.
    try:
        adapter_import = Path(os.path.relpath(adapter, destination)).as_posix()
    except ValueError as exc:
        raise ValueError('OMP requires its generated plugin and the LCU release on the same filesystem drive.') from exc
    if not adapter_import.startswith('.'):
        adapter_import = './' + adapter_import
    wrapper = ('import lcu from ' + json.dumps(adapter_import) + ';\n'
               'export default pi => lcu(pi, {command: ' + json.dumps(command) +
               ', connectOnLoad: true, ompEssentialTools: true});\n')
    files = {'package.json': (json.dumps(manifest, indent=2) + '\n').encode(),
             'index.ts': wrapper.encode()}
    with _package(destination, 'omp', files, skill) as package:
        _run([executable, 'plugin', 'link', str(package)], cwd=home, env=env)


def configure_hermes(home, skill, command, node, release, *, scope, project, env):
    if scope != 'user':
        raise ValueError('Hermes native plugins are profile-scoped. Use --scope user with the intended HERMES_HOME; project scope is not supported.')
    executable = shutil.which('hermes', path=env.get('PATH'))
    if not executable:
        raise ValueError('Hermes is not on the target account PATH. Install Hermes, then rerun `lcu setup --agent hermes`.')
    root = Path(env.get('HERMES_HOME') or home / '.hermes')
    if not root.is_absolute():
        raise ValueError('HERMES_HOME must be absolute.')
    source = release / 'adapters/hermes'
    files = {}
    for name in ('plugin.yaml', '__init__.py'):
        if not (source / name).is_file():
            raise ValueError(f'LCU Hermes plugin missing: {source / name}')
        files[name] = (source / name).read_bytes()
    bridge = source / 'bridge.mjs'
    if not bridge.is_file():
        raise ValueError(f'LCU Hermes bridge missing: {bridge}')
    config = {'command': command, 'node': str(node), 'bridge': str(bridge)}
    files['lcu-config.json'] = (json.dumps(config, indent=2) + '\n').encode()
    with _package(root / 'plugins/lcu-cua', 'hermes', files, skill):
        _run([executable, 'plugins', 'enable', 'lcu-cua'], cwd=home,
             env={**env, 'HERMES_HOME': str(root)})
