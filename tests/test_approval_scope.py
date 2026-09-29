"""Manual approval records the same scope the autonomous publish path would."""
from pathlib import Path
import tempfile
import unittest

from dcsa_custodian.common import read_json, write_json
from dcsa_custodian.release import approval_scope, approve_candidate
from dcsa_custodian.release_contract import STATE


class ApprovalScopeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)

    def candidate(self, release_id: str, source_intake_files: list[str]) -> Path:
        release_dir = Path(self.temporary.name) / release_id
        write_json(release_dir / "VALIDATION.json", {"valid": True, "publishable": True, "publication_blockers": []})
        write_json(release_dir / "production" / STATE, {"release_id": release_id, "source_intake_files": source_intake_files})
        return release_dir

    def test_derived_only_release_is_approved_as_derived_artifacts_only(self):
        release_dir = self.candidate("derived-only", [])
        receipt = approve_candidate(release_dir, "tester", "derived only")
        self.assertEqual(receipt["scope"], "derived_artifacts_only")
        self.assertEqual(read_json(release_dir / "APPROVAL.json")["scope"], "derived_artifacts_only")
        self.assertEqual(approval_scope(release_dir), receipt["scope"])

    def test_source_intake_release_is_approved_as_source_intake_and_derived(self):
        release_dir = self.candidate("source-intake", ["intake/new-guidance.pdf"])
        receipt = approve_candidate(release_dir, "tester", "with intake")
        self.assertEqual(receipt["scope"], "source_intake_and_derived")
        self.assertEqual(read_json(release_dir / "APPROVAL.json")["scope"], "source_intake_and_derived")
        self.assertEqual(approval_scope(release_dir), receipt["scope"])


if __name__ == "__main__":
    unittest.main()
