"""ASAR gates reject drift in internal code, archive structure, and manifests."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from inventory_asar import capture_asar, verify_asar, verify_shared_sources


class AsarInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'scripts').mkdir()
        self.asar = self.root/'app.asar'
        self.package = b'{"name":"fixture","exports":{".":"./main.js"},"dependencies":{"original":"1"}}'
        self.external_package = b'{"name":"native-fixture","main":"native.js","optionalDependencies":{"native":"2"}}'
        self.unpacked = Path(str(self.asar)+'.unpacked')/'native/package.json'
        self.unpacked.parent.mkdir(parents=True)
        self.unpacked.write_bytes(self.external_package)
        self.extra = {}
        self.write_archive()
        self.record()

    def write_archive(self, alter=None):
        data, header = bytearray(), {'files': {'empty': {'files': {}}, 'alias.js': {'link':'main.js'}}}
        for name, content in {'main.js':b'export const original = true;', 'package.json':self.package, **self.extra}.items():
            header['files'][name] = {'size':len(content), 'offset':str(len(data)),
                'integrity':{'algorithm':'SHA256','hash':hashlib.sha256(content).hexdigest()}}
            data.extend(content)
        header['files']['native'] = {'files': {'package.json': {'size':len(self.external_package), 'unpacked':True,
            'integrity':{'algorithm':'SHA256','hash':hashlib.sha256(self.external_package).hexdigest()}}}}
        if alter:
            alter(header)
        encoded = json.dumps(header,separators=(',',':')).encode()
        padding = b'\0' * (-len(encoded)%4)
        header_size = 8+len(encoded)+len(padding)
        self.asar.write_bytes(struct.pack('<4I',4,header_size,header_size-4,len(encoded))+encoded+padding+data)
        application = {'package_version':'fixture','official_package_sha256':'checked-by-parent-gate','files': {
            'resources/app.asar': {'kind':'file','size':self.asar.stat().st_size,'sha256':hashlib.sha256(self.asar.read_bytes()).hexdigest()},
            'resources/app.asar.unpacked/native/package.json': {'kind':'file','size':len(self.external_package),
                'sha256':hashlib.sha256(self.external_package).hexdigest()}}}
        (self.root/'scripts/application-inventory.arm64.json').write_text(json.dumps(application))

    def record(self):
        record = capture_asar(self.asar,'arm64',self.root)
        (self.root/'scripts/asar-inventory.arm64.json').write_text(json.dumps(record))

    def test_all_entries_and_both_package_interfaces_are_recorded(self):
        record = verify_asar(self.asar,'arm64',self.root)
        self.assertEqual(set(record['files']), {'main.js','package.json','native','native/package.json','empty','alias.js'})
        self.assertEqual(record['files']['main.js']['sha256'],hashlib.sha256(b'export const original = true;').hexdigest())
        self.assertEqual(record['files']['alias.js']['target'],'main.js')
        self.assertEqual(record['files']['empty']['kind'],'directory')
        self.assertTrue(record['files']['native/package.json']['unpacked'])
        self.assertEqual(record['surface']['package_interfaces']['package.json']['exports'],{'.':'./main.js'})
        self.assertEqual(record['surface']['package_interfaces']['native/package.json']['optionalDependencies'],{'native':'2'})

    def test_changed_archive_is_rejected_by_application_binding(self):
        with self.asar.open('ab') as stream:
            stream.write(b'changed')
        with self.assertRaisesRegex(ValueError,'complete application inventory'):
            verify_asar(self.asar,'arm64',self.root)

    def test_incorrect_internal_hash_is_rejected(self):
        self.write_archive(lambda h:h['files']['main.js']['integrity'].update(hash='0'*64))
        with self.assertRaisesRegex(ValueError,'content integrity mismatch: main.js'):
            capture_asar(self.asar,'arm64',self.root)

    def test_out_of_bounds_packed_range_is_rejected(self):
        self.write_archive(lambda h:h['files']['main.js'].update(offset='999999999'))
        with self.assertRaisesRegex(ValueError,'outside archive: main.js'):
            capture_asar(self.asar,'arm64',self.root)

    def test_unpacked_package_reference_must_match_architecture_pin(self):
        self.unpacked.write_bytes(b'{"name":"replacement"}')
        with self.assertRaisesRegex(ValueError,'package manifest differs from pinned bytes'):
            capture_asar(self.asar,'arm64',self.root)

    def test_added_internal_provider_requires_an_inventory_update(self):
        self.extra['new-provider.js'] = b'new upstream provider'
        self.write_archive()
        with self.assertRaisesRegex(ValueError,'added=.*new-provider.js'):
            verify_asar(self.asar,'arm64',self.root)

    def test_changed_renderer_between_architectures_is_rejected(self):
        names = ['.vite/build/browser-page-preload.js','.vite/build/preload.js','webview/assets/controller.js']
        record = {'files':{name:{'size':5,'sha256':'original'} for name in names},
                  'surface':{'application_source_modules':names}}
        for arch in ('arm64','x64'):
            (self.root/f'scripts/asar-inventory.{arch}.json').write_text(json.dumps(record))
        self.assertEqual(verify_shared_sources(self.root),3)
        record['files'][names[-1]]['sha256']='changed'
        (self.root/'scripts/asar-inventory.x64.json').write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError,'source differs between architectures'):
            verify_shared_sources(self.root)


if __name__ == '__main__':
    unittest.main()
