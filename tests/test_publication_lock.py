"""Publication exclusion across processes, with no live corpus access."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from dcsa_custodian.publication_lock import publication_lock
from dcsa_custodian.release import publish_candidate


class PublicationLockTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "library"
        self.root.mkdir()

    def child(self, root):
        source = Path(__file__).resolve().parents[1] / "src"
        code = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from dcsa_custodian.publication_lock import publication_lock
try:
    with publication_lock(Path(sys.argv[2])):
        print('acquired', flush=True)
except RuntimeError:
    print('contended', flush=True)
    sys.exit(3)
"""
        return subprocess.run([sys.executable, "-c", code, str(source), str(root)],
                              capture_output=True, text=True, timeout=15)

    def test_cross_process_exclusion_and_release_without_corpus_mutation(self):
        with publication_lock(self.root):
            blocked = self.child(self.root / ".." / "library")
            self.assertEqual(blocked.returncode, 3, blocked.stderr)
            self.assertIn("contended", blocked.stdout)
            other = self.base / "other-library"
            other.mkdir()
            independent = self.child(other)
            self.assertEqual(independent.returncode, 0, independent.stderr)
        acquired = self.child(self.root)
        self.assertEqual(acquired.returncode, 0, acquired.stderr)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_exception_releases_lock_and_persistent_file_is_reusable(self):
        with self.assertRaisesRegex(ValueError, "synthetic failure"):
            with publication_lock(self.root):
                raise ValueError("synthetic failure")
        self.assertTrue((self.base / ".library.custodian-publish.lock").is_file())
        acquired = self.child(self.root)
        self.assertEqual(acquired.returncode, 0, acquired.stderr)

    def test_publish_and_preview_hold_lock_before_preflight_and_release_on_failure(self):
        def preflight(*args, **kwargs):
            blocked = self.child(self.root)
            self.assertEqual(blocked.returncode, 3, blocked.stderr)
            raise ValueError("synthetic preflight failure")

        for dry_run in (False, True):
            with self.subTest(dry_run=dry_run):
                with patch("dcsa_custodian.release.validate_candidate", side_effect=preflight):
                    with self.assertRaisesRegex(ValueError, "synthetic preflight failure"):
                        publish_candidate(self.base, self.root, {}, self.base / "candidate", dry_run)
                self.assertEqual(self.child(self.root).returncode, 0)


if __name__ == "__main__":
    unittest.main()
