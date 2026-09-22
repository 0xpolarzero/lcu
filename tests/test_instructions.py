import copy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from project_instructions import project_text, verify_outputs


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


class InstructionProjectionTests(unittest.TestCase):
    def setUp(self):
        self.source = 'Keep first rule.\nOther platform.\nKeep last rule.\n'
        self.expected = self.source
        self.entry = {
            'source': 'upstream.md', 'sha256': digest(self.source),
            'output_sha256': digest(self.expected), 'targets': ['instructions/api.md'],
            'edits': [],
        }

    def test_unchanged_rules_survive_exactly(self):
        self.assertEqual(project_text(self.source.encode(), self.entry), self.expected.encode())

    def test_upstream_drift_fails_before_projection(self):
        with self.assertRaisesRegex(ValueError, 'Upstream instruction'):
            project_text((self.source + 'new rule\n').encode(), self.entry)

    def test_output_hash_must_match_unchanged_source(self):
        entry = copy.deepcopy(self.entry)
        entry['output_sha256'] = digest('A summary')
        with self.assertRaisesRegex(ValueError, 'differs from upstream'):
            project_text(self.source.encode(), entry)

    def test_runtime_instruction_rewriting_is_rejected(self):
        entry = copy.deepcopy(self.entry)
        entry['edits'] = [{'replacement': 'A rewritten instruction'}]
        with self.assertRaisesRegex(ValueError, 'edits are not allowed'):
            project_text(self.source.encode(), entry)

    def test_manual_condensation_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'instructions').mkdir()
            path = root / 'instructions/api.md'
            path.write_text(self.expected)
            verify_outputs(root, [self.entry])
            path.write_text('A shorter summary.\n')
            with self.assertRaisesRegex(ValueError, 'Instruction drift'):
                verify_outputs(root, [self.entry])
