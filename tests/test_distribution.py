"""Source distribution must not carry copied installed-app payloads."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SourceDistributionTests(unittest.TestCase):
    def test_upstream_instructions_and_iab_host_are_install_time_only(self):
        for relative in ('instructions', 'skills/lcu/references', 'lcu/host'):
            with self.subTest(relative=relative):
                self.assertFalse((ROOT / relative).exists(), relative)


if __name__ == '__main__':
    unittest.main()
