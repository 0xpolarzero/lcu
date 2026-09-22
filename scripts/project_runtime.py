"""Bundle the complete official Linux runtime without rewriting or tree shaking it."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from urllib.request import Request, urlopen
from project_instructions import project as project_instructions


def download(url, path, digest):
    hasher = hashlib.sha256()
    request = Request(url, headers={'User-Agent': 'lcu/0.3.0-dev'})
    with urlopen(request, timeout=60) as response, path.open('xb') as output:
        while data := response.read(1024 * 1024):
            hasher.update(data)
            output.write(data)
    if hasher.hexdigest() != digest:
        raise ValueError(f'Integrity check failed: {url}. No downloaded code was executed.')


def provision(release, source, scratch, arch, package=None):
    lock = json.loads((source / 'runtime.lock.json').read_text())
    entry = lock['architectures'][arch]
    deb = Path(package) if package else scratch / 'chatgpt.deb'
    if package:
        if hashlib.file_digest(deb.open('rb'), 'sha256').hexdigest() != entry['sha256']:
            raise ValueError('Local official package checksum mismatch')
    else:
        download(lock['source'].format(deb_arch=entry['deb_arch']), deb, entry['sha256'])
    extracted = scratch / 'upstream'
    subprocess.run(['dpkg-deb', '--extract', str(deb), str(extracted)], check=True)
    runtime = extracted / 'usr/lib/chatgpt/resources/cua_node'
    manifest = json.loads((runtime / 'manifest.json').read_text())
    if manifest['platform'] != 'linux' or manifest['arch'] != arch or manifest['runtime_archive_version'] != lock['runtime']:
        raise ValueError('Unexpected official runtime manifest')
    from inventory_runtime import verify as verify_runtime
    verify_runtime(runtime, arch)
    project_instructions(runtime / 'lib/node_modules', source)
    host = release / 'host'
    (host / 'bin').mkdir(parents=True)
    resources = extracted / 'usr/lib/chatgpt/resources'
    from inventory_runtime import verify_host, verify_host_copy, verify_application
    verify_host(resources, arch)
    # The in-app browser depends on the original Owl Electron shell and app.asar.
    # Keep the complete application, with aliases instead of duplicate runtimes.
    application = host / 'application'
    shutil.move(str(extracted / 'usr/lib/chatgpt'), application)
    verify_application(application, arch)
    from inventory_asar import verify_asar
    verify_asar(application / 'resources/app.asar', arch)
    (release / 'runtime').symlink_to('host/application/resources/cua_node')
    for name in ('codex', 'codex-code-mode-host'):
        (host / 'bin' / name).symlink_to('../application/resources/' + name)
    (host / 'plugins').mkdir()
    for name in ('browser', 'chrome', 'unified-computer-use'):
        (host / 'plugins' / name).symlink_to('../application/resources/plugins/openai-bundled/plugins/' + name)
    verify_runtime(release / 'runtime', arch)
    verify_host_copy(host, arch)
    subprocess.run([str(release / 'runtime/bin/node'), '--expose-internals',
                    str(source / 'scripts/extract_iab_host.cjs'), str(application), str(host / 'iab')], check=True)
    notices = host / 'upstream-notices'
    notices.mkdir()
    for path in [*extracted.rglob('*'), *application.rglob('*')]:
        if path.is_file() and path.name.lower().startswith(('license', 'copyright', 'notice')):
            relative = path.relative_to(extracted) if path.is_relative_to(extracted) else Path('usr/lib/chatgpt') / path.relative_to(application)
            target = notices / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    (release / 'provenance.json').write_text(json.dumps({
        'official_package_sha256': entry['sha256'], 'architecture': arch,
        'package_version': lock['version'],
        'runtime': lock['runtime'],
        'treatment': 'Unchanged complete /usr/lib/chatgpt application, runtime and plugins; original IAB declarations exposed through a standalone host adapter',
    }, indent=2) + '\n')
