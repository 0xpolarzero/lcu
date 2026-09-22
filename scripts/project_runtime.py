"""Select and specialize the official Linux runtime; never implement UI actions."""
import base64
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
from urllib.request import Request, urlopen


def download(url, path, digest, algorithm='sha256'):
    hasher = hashlib.new(algorithm)
    request = Request(url, headers={'User-Agent': 'lcu/0.2.0'})
    with urlopen(request, timeout=60) as response, path.open('xb') as output:
        while data := response.read(1024 * 1024):
            hasher.update(data)
            output.write(data)
    expected = bytes.fromhex(digest) if algorithm == 'sha256' else base64.b64decode(digest)
    if hasher.digest() != expected:
        raise ValueError(f'Integrity check failed: {url}. No downloaded code was executed.')


def replace(path, before, after):
    text = path.read_text()
    if text.count(before) != 1:
        raise ValueError(f'Upstream source changed: {path.name}: expected one {before!r}')
    path.write_text(text.replace(before, after))


def remove_arm(path, start, end):
    text = path.read_text()
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f'Upstream dispatch changed: {path}')
    left, right = text.index(start), text.index(end)
    if right <= left:
        raise ValueError(f'Upstream dispatch reordered: {path}')
    path.write_text(text[:left] + text[right:])


def project(source, destination, esbuild, instructions, arch):
    modules = source / 'lib/node_modules/@oai'
    # Modify the extracted scratch copy, never the package or an active release.
    for package in ('sky', 'cua'):
        sky = modules / package / 'dist/project/cua/sky_js/src'
        (sky / 'create_client.js').write_text('export {create_client} from "./targets/linux/create_client.js";\n')
        replace(sky / 'load_options.js', 'switch(process.platform)', 'switch("linux")')
        replace(sky / 'load_options.js', 'case"darwin":return{target:"mac"};', '')
        replace(sky / 'load_options.js', 'case"win32":return{target:"windows"};', '')
    cua = modules / 'cua/dist/lib/js/oai_js_cua/src'
    replace(cua / 'tinysky_alt/create_tinysky_alt.js', '!1!==c.browser?', 'false?')
    replace(cua / 'tinysky_alt/create_tinysky_alt.js', 'if(void 0!==S)', 'if(false)')
    replace(cua / 'tinysky_alt/create_tinysky_alt.js', 'const O=T.target;', 'const O="linux";')
    remove_arm(cua / 'tinysky_alt/create_tinysky_alt.js', 'case"mac":Object.assign(E', 'case"linux":Object.assign(E')
    remove_arm(cua / 'tinysky_alt/create_tinysky_alt.js', 'case"windows":Object.assign(E', 'default:throw new t(O)')
    replace(cua / 'get_apps.js', 'const s=e.target;', 'const s="linux";')
    replace(cua / 'get_apps.js', 'case"windows":case"mac":return e.list_apps();', '')
    replace(cua / 'get_state.js', 'if(void 0===r)', 'if(true)')
    repl = modules / 'cua-repl/dist/lib/js/oai_js_cua_repl/src'
    replace(repl / 'instructions.js', 'const s=e[r];', 'const s="linux";')
    replace(repl / 'instructions.js', 'browser:o("cloud"===t||"orbit"===t?`${s}/browser-cloud`:`${s}/browser`)', 'browser:""')
    entries = {
        'cua': (cua / 'tinysky_alt/globals.js', {'./tinyskyAlt': './index.js'}),
        'sky': (modules / 'sky/dist/project/cua/sky_js/src/service.js', {'./service': './index.js'}),
        'cua-repl': (repl / 'index.js', {'.': './index.js'}),
    }
    for name, (entry, exports) in entries.items():
        out = destination / f'lib/node_modules/@oai/{name}'
        out.mkdir(parents=True)
        metadata = json.loads((modules / name / 'package.json').read_text())
        metadata = {k: metadata[k] for k in ('name', 'version', 'author', 'type') if k in metadata}
        metadata.update(exports=exports, imports={'#instructions/*': './instructions/*'})
        (out / 'package.json').write_text(json.dumps(metadata, indent=2) + '\n')
        subprocess.run([str(esbuild), str(entry), '--bundle', '--platform=node', '--format=esm',
                        '--target=node24', '--minify-syntax', '--tree-shaking=true',
                        '--external:#instructions/*', '--legal-comments=inline',
                        f'--outfile={out / "index.js"}', f'--metafile={out / "build-inputs.json"}'], check=True)
        inputs = json.loads((out / 'build-inputs.json').read_text())['inputs']
        forbidden = ('/targets/mac/', '/targets/windows/', 'oai_js_browser/', 'browser-desktop')
        if any(any(word in path for word in forbidden) for path in inputs):
            raise ValueError(f'Non-Linux dependency survived projection: {name}')
        code = (out / 'index.js').read_text()
        if any(word in code for word in ('macOS', 'case "mac"', 'case "windows"', 'setupBrowserRuntime', 'createBrowserTab')):
            raise ValueError(f'Non-Linux implementation survived projection: {name}')
    shutil.copytree(instructions / 'repl', destination / 'lib/node_modules/@oai/cua-repl/instructions')
    shutil.copytree(instructions / 'api', destination / 'lib/node_modules/@oai/cua/docs')
    # Preserve the upstream confirmation policy, without broadening agent authority.
    shutil.copyfile(modules / 'cua/docs/tinysky-alt-confirmations.md',
                    destination / 'lib/node_modules/@oai/cua/docs/tinysky-alt-confirmations.md')
    for name in ('node', 'node_repl'):
        out = destination / 'bin' / name
        out.parent.mkdir(exist_ok=True)
        shutil.copy2(source / 'bin' / name, out)
    binary = destination / f'lib/node_modules/@oai/sky/bin/linux/sky_linux_{arch}'
    binary.parent.mkdir(parents=True)
    shutil.copy2(modules / f'sky/bin/linux/sky_linux_{arch}', binary)
    # The untrusted client retains its original standalone fallback but uses RPC in the REPL.
    other = destination / f'lib/node_modules/@oai/cua/bin/linux'
    other.mkdir(parents=True)
    (other / binary.name).symlink_to(f'../../../sky/bin/linux/{binary.name}')
    shutil.copy2(source / 'manifest.json', destination / 'upstream-manifest.json')


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
    builder = scratch / 'esbuild.tgz'
    dist = entry['esbuild']
    download(dist['tarball'], builder, dist['integrity'].removeprefix('sha512-'), 'sha512')
    with tarfile.open(builder) as archive:
        archive.extractall(scratch / 'esbuild', filter='data')
    project(runtime, release / 'runtime', scratch / 'esbuild/package/bin/esbuild', source / 'instructions', arch)
    notices = release / 'runtime/upstream-notices'
    notices.mkdir()
    for path in extracted.rglob('*'):
        if path.is_file() and path.name.lower().startswith(('license', 'copyright', 'notice')):
            relative = path.relative_to(extracted)
            target = notices / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    (release / 'runtime/provenance.json').write_text(json.dumps({
        'official_package_sha256': entry['sha256'], 'architecture': arch,
        'package_version': lock['version'], 'runtime': lock['runtime'],
        'projection': 'Linux native computer only; original Node REPL and Sky binary',
    }, indent=2) + '\n')
