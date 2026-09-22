import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from inventory_runtime import capture, inventory, surface, verify, verify_application
from project_instructions import digest, project


class RuntimeInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.runtime = self.root / 'runtime'
        self.runtime.mkdir()
        (self.root / 'scripts').mkdir()
        (self.root / 'runtime.lock.json').write_text(json.dumps({
            'version': 'fixture', 'runtime': 'fixture-runtime',
            'architectures': {'arm64': {'sha256': 'verified-by-build'}},
        }))
        (self.runtime / 'manifest.json').write_text(json.dumps({
            'platform': 'linux', 'arch': 'arm64',
            'runtime_archive_version': 'fixture-runtime',
        }))
        self.code = self.runtime / 'client.js'
        self.code.write_text('export const supported = true;\n')
        (self.runtime / 'empty-resources').mkdir()
        self.record()

    def record(self):
        (self.root / 'scripts/runtime-inventory.arm64.json').write_text(
            json.dumps(capture(self.runtime, 'arm64', self.root)))

    def check(self):
        return verify(self.runtime, 'arm64', self.root)

    def test_unchanged_runtime_including_empty_directories_passes(self):
        self.check()
        self.assertEqual(inventory(self.runtime)['empty-resources']['kind'], 'directory')

    def test_missing_runtime_code_is_rejected(self):
        self.code.unlink()
        with self.assertRaisesRegex(ValueError, 'missing=.*client.js'):
            self.check()

    def test_new_unclassified_file_is_rejected(self):
        (self.runtime / 'new-provider.js').write_text('export const added = true;')
        with self.assertRaisesRegex(ValueError, 'added=.*new-provider.js'):
            self.check()

    def test_modified_implementation_is_rejected(self):
        self.code.write_text('export const supported = false;\n')
        with self.assertRaisesRegex(ValueError, 'changed=.*client.js'):
            self.check()

    def test_lost_executable_permission_is_rejected(self):
        os.chmod(self.code, 0o755)
        self.record()
        os.chmod(self.code, 0o644)
        with self.assertRaisesRegex(ValueError, 'changed=.*client.js'):
            self.check()

    def test_symlink_target_is_recorded_without_following_directory(self):
        link = self.runtime / 'provider'
        link.symlink_to('empty-resources', target_is_directory=True)
        self.record()
        self.assertEqual(inventory(self.runtime)['provider']['target'], 'empty-resources')
        link.unlink()
        link.symlink_to('different-target', target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'changed=.*provider'):
            self.check()

    def test_missing_capability_conditional_document_is_rejected(self):
        references = self.runtime / 'lib/node_modules/@oai/browser-desktop/environment-docs/codex-app'
        references.mkdir(parents=True)
        (references / 'documents.json').write_text(json.dumps([{
            'name': 'file-uploads', 'mode': 'lookup',
            'when': {'requiredApiMembers': ['PlaywrightFileChooser.setFiles']},
        }]))
        with self.assertRaisesRegex(ValueError, 'missing resource.*file-uploads.md'):
            surface(self.runtime, inventory(self.runtime))

    def test_full_application_rejects_changes_outside_cua_node(self):
        application = self.root / 'application'
        (application / 'resources').mkdir(parents=True)
        source = application / 'resources/app.asar'
        source.write_bytes(b'original browser host implementation')
        expected = {'files': inventory(application),
                    'root_mode': application.stat().st_mode & 0o7777}
        (self.root / 'scripts/application-inventory.arm64.json').write_text(json.dumps(expected))
        verify_application(application, 'arm64', self.root)
        source.write_bytes(b'incomplete replacement browser host')
        with self.assertRaisesRegex(ValueError, 'changed=.*resources/app.asar'):
            verify_application(application, 'arm64', self.root)

    def test_full_application_rejects_omitted_unknown_resources(self):
        application = self.root / 'application'
        application.mkdir()
        source = application / 'new-upstream-host.so'
        source.write_bytes(b'new dependency')
        expected = {'files': inventory(application),
                    'root_mode': application.stat().st_mode & 0o7777}
        (self.root / 'scripts/application-inventory.arm64.json').write_text(json.dumps(expected))
        source.unlink()
        with self.assertRaisesRegex(ValueError, 'missing=.*new-upstream-host.so'):
            verify_application(application, 'arm64', self.root)


class InstructionInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.modules = self.root / 'original/cua_node/lib/node_modules'
        self.guides = self.modules / '@oai/cua/docs'
        self.guides.mkdir(parents=True)
        data = b'Original supported workflow.\n'
        (self.guides / 'core.md').write_bytes(data)
        (self.root / 'scripts').mkdir()
        (self.root / 'instructions').mkdir()
        (self.root / 'instructions/core.md').write_bytes(data)
        self.manifest = {'format': 2,
                         'resource_roots': [{'scope': 'modules', 'source': '@oai/cua/docs'}],
                         'files': [{'source': '@oai/cua/docs/core.md', 'sha256': digest(data),
                                    'targets': ['instructions/core.md'], 'edits': [],
                                    'output_sha256': digest(data)}]}
        self.record()

    def record(self):
        (self.root / 'scripts/instructions.lock.json').write_text(json.dumps(self.manifest))

    def test_new_guide_cannot_be_silently_omitted(self):
        project(self.modules, self.root)
        (self.guides / 'new-linux-capability.md').write_text('Required new API guidance.\n')
        with self.assertRaisesRegex(ValueError, 'unclassified=.*new-linux-capability.md'):
            project(self.modules, self.root)

    def test_deleted_guide_is_rejected(self):
        (self.guides / 'core.md').unlink()
        with self.assertRaisesRegex(ValueError, 'missing=.*core.md'):
            project(self.modules, self.root)

    def test_rewriting_original_instructions_is_rejected(self):
        self.manifest['files'][0]['edits'] = [{
            'start': 1, 'end': 1, 'replacement': 'A shorter summary.\n', 'reason': 'Condense it',
        }]
        self.record()
        with self.assertRaisesRegex(ValueError, 'rewrites are forbidden'):
            project(self.modules, self.root)


if __name__ == '__main__':
    unittest.main()
