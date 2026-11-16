"""voi-intake-plan: a Librarian package becomes a reviewed plan stage_intake accepts, reproducibly, offline."""
from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dcsa_custodian import voi_intake
from dcsa_custodian.common import read_json, sha256_file, write_json
from dcsa_custodian.intake import stage_intake
from dcsa_custodian.voi_intake import PYPDF_VERSION, build_voi_plan, masthead_period
import test_custodian

MASTHEAD = ["October 2026", "www.dcsa.mil", "Dear Facility Security Officer (FSO):",
            "DCSA publishes the monthly Voice of Industry (VOI) newsletter.", "TABLE OF CONTENTS",
            "SECURITY REVIEW RATING RESULTS 2"]
SECOND = ["SECURITY REVIEW RATING RESULTS", "Results current as of October 27, 2026.", "Initial Security Review Within 12 months"]


def make_pdf(pages: list[list[str]]) -> bytes:
    """A small real PDF with one text line per entry, so the pinned extractor has something to read."""
    def escape(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(len(pages)))
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode(),
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    for index, lines in enumerate(pages):
        operators = ["BT", "/F1 11 Tf", "72 740 Td"]
        for line in lines:
            operators += [f"({escape(line)}) Tj", "0 -14 Td"]
        stream = "\n".join(operators + ["ET"]).encode("latin-1")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> "
                       f"/Contents {5 + 2 * index} 0 R >>".encode())
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    output, offsets = bytearray(b"%PDF-1.4\n"), []
    for number, body in enumerate(objects, 1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    start = len(output)
    output += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    output += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    output += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
    return bytes(output)


class VoiIntakePlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.library, self.quarantine, self.out = base / "library", base / "quarantine", base / "state/incoming/voi"
        self.library.mkdir()
        self.quarantine.mkdir()
        test_custodian.CustodianTests().make_library(self.library)
        manifest = self.library / "ROBOT_READABLE_DIRECTORY/MANIFESTS/documents.jsonl"
        folder = "INDUSTRIAL_SECURITY/VOICE_OF_INDUSTRY_VOI/Voice of Industry - September 2026 Newsletter"
        with manifest.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps({"document_id": "dcsa-voi-2026-09-voi", "collection_id": "voi", "domain": "industrial_security",
                                     "authority_tier": 7, "current_status": "current_or_verify",
                                     "human_source_path": f"HUMAN_READABLE_DIRECTORY/{folder}.pdf",
                                     "robot_text_path": f"ROBOT_READABLE_DIRECTORY/TEXT/{folder}.txt"}) + "\n")
        self.pages = [MASTHEAD, SECOND]

    def package(self, pages=None, name="261030_VOI_Newsletter.pdf", **fields) -> Path:
        source = self.quarantine / name
        source.write_bytes(make_pdf(pages or self.pages))
        package = {"producer_id": "dcsa-librarian", "approval_state": "quarantined_unreviewed", "source_filename": name,
                   "requested_source_uri": "https://www.dcsa.mil/tools/261030%20VOI%20Newsletter.pdf",
                   "resolved_source_uri": "https://www.dcsa.mil/tools/261030%20VOI%20Newsletter.pdf",
                   "retrieved_at": "2026-11-15T12:59:48Z", "mime_type": "application/pdf",
                   "source_sha256": sha256_file(source), "source_bytes": source.stat().st_size, "publisher_claim": "October 2026"}
        package.update(fields)
        write_json(self.quarantine / f"{name}.intake.json", package)
        return self.quarantine / f"{name}.intake.json"

    def independent(self, pages=None):
        return lambda pdf: (["\n".join(lines) for lines in (pages or self.pages)], "test extractor 1.0")

    def plan(self, package: Path, out: Path | None = None, **options):
        return build_voi_plan(self.library, package, out or self.out, options.pop("independent", self.independent()), **options)

    def test_the_plan_needs_no_hand_written_json_and_stage_intake_accepts_it(self) -> None:
        summary = self.plan(self.package())
        self.assertEqual((summary["status"], summary["period"], summary["document_id"]),
                         ("plan_ready", "2026-10", "dcsa-voi-2026-10-voi"))
        item = read_json(self.out / "plan.json")["items"][0]
        record = item["record"]
        self.assertEqual(record["title"], "Voice of Industry - October 2026 Newsletter")
        self.assertTrue(record["human_source_path"].endswith("VOICE_OF_INDUSTRY_VOI/Voice of Industry - October 2026 Newsletter.pdf"))
        self.assertTrue(record["robot_text_path"].endswith("VOICE_OF_INDUSTRY_VOI/Voice of Industry - October 2026 Newsletter.txt"))
        text = (self.out / item["robot_file"]).read_bytes().decode("utf-8")
        self.assertNotIn("\r", text)
        self.assertTrue(text.startswith("MACHINE-READABLE TEXT COPY\nSource PDF: Voice of Industry - October 2026 Newsletter.pdf\n"))
        self.assertEqual(re.findall(r"\f\n===== SOURCE PAGE (\d+) =====\n\n", text), ["1", "2"])
        self.assertIn("Results current as of October 27, 2026.", text.split("\f")[2])
        self.assertTrue(read_json(self.out / "extraction-report.json")["parity"]["passed"])
        for field in ("identity", "provenance", "extraction", "parity", "taxonomy", "lifecycle"):
            self.assertTrue(item["review"][field])
        self.assertIn("masthead (SOURCE PAGE 1, line 1: 'October 2026')", item["review"]["lifecycle"])
        self.assertIn("publisher_claim 'October 2026' agrees", item["review"]["lifecycle"])
        self.assertIn("no Librarian confirm-period receipt", item["review"]["lifecycle"])
        staged = Path(self.temp.name) / "staged"
        changed = stage_intake(self.library, staged, self.out / "plan.json")
        self.assertIn(record["robot_text_path"], changed)
        rows = [json.loads(line) for line in (staged / "ROBOT_READABLE_DIRECTORY/MANIFESTS/documents.jsonl").read_text(encoding="utf-8").splitlines()]
        added = next(row for row in rows if row["document_id"] == "dcsa-voi-2026-10-voi")
        self.assertEqual((added["title"], added["robot_sha256"]), (record["title"], summary["robot_sha256"]))
        # the library itself was only read
        self.assertFalse((self.library / record["robot_text_path"]).exists())

    def test_the_same_source_bytes_give_the_same_text_bytes(self) -> None:
        package = self.package()
        first = self.plan(package)
        second = self.plan(package, Path(self.temp.name) / "again", reviewed_by="another reviewer")
        self.assertEqual(first["robot_sha256"], second["robot_sha256"])
        text = Path(first["robot_file"]).read_text(encoding="utf-8")
        self.assertNotRegex(text.split("\f")[0], r"generated|retrieved|20\d\d-\d\d-\d\d")
        self.assertIn(f"pypdf {PYPDF_VERSION} (pinned)", text)

    def test_the_extractor_version_is_pinned_and_checked(self) -> None:
        import pypdf
        self.assertEqual(pypdf.__version__, PYPDF_VERSION, "the test interpreter must carry the pinned extractor")
        pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn(f'"pypdf=={PYPDF_VERSION}"', pyproject)
        package = self.package()
        with patch.object(pypdf, "__version__", "6.21.4"):
            with self.assertRaisesRegex(RuntimeError, "pinned to pypdf"):
                self.plan(package)
        self.assertFalse(self.out.exists())

    def test_the_period_comes_from_the_masthead_never_the_file_name(self) -> None:
        # The download is named for November; the issue says October.
        summary = self.plan(self.package(name="261130_VOI_Newsletter.pdf"))
        self.assertEqual(summary["title"], "Voice of Industry - October 2026 Newsletter")
        self.assertEqual(masthead_period(" October 2026 \nVoice of Industry\nTABLE OF CONTENTS\nMarch 2021")["period"], "2026-10")
        for page, message in (("www.dcsa.mil\nVoice of Industry\nTABLE OF CONTENTS\nOctober 2026", "states no issue month"),
                              ("October 2026\nNovember 2026\nVoice of Industry", "more than one period"),
                              ("October 2026\nwww.dcsa.mil", "does not identify"),
                              ("11 September 2023\nSPECIAL BULLETIN\nVoice of Industry", "bulletin")):
            with self.assertRaisesRegex(ValueError, message):
                masthead_period(page)

    def test_a_publisher_claim_that_disagrees_stops_the_command(self) -> None:
        with self.assertRaisesRegex(ValueError, "period mismatch.*publisher_claim says 'September 2026'"):
            self.plan(self.package(publisher_claim="September 2026"))
        self.assertFalse(self.out.exists())
        summary = self.plan(self.package(publisher_claim="Voice of Industry newsletter"))
        self.assertTrue(any("states no month and year" in line for line in summary["period_evidence"]))

    def test_a_confirm_period_receipt_is_cross_checked(self) -> None:
        package = self.package()
        digest = read_json(package)["source_sha256"]
        marker = self.quarantine / "2026-10.json"

        def write(period="2026-10", verified=True, sha=digest):
            write_json(marker, {"job_id": "voi-watch", "period": period, "evidence": {
                "issue_period_verified": verified, "source_period": period, "source_sha256": sha,
                "reviewed_by": "librarian-review", "issue_locator": "page 1 masthead"}})
        for arguments, message in (({"period": "2026-09"}, "confirm-period receipt says 2026-09"),
                                   ({"verified": False}, "does not record a verified"),
                                   ({"sha": "0" * 64}, "different source bytes")):
            write(**arguments)
            with self.assertRaisesRegex(ValueError, message):
                self.plan(package, confirm_period=marker)
            self.assertFalse(self.out.exists())
        write()
        summary = self.plan(package, confirm_period=marker)
        self.assertTrue(any("confirm-period receipt agrees" in line for line in summary["period_evidence"]))
        self.assertIn(sha256_file(marker), read_json(self.out / "plan.json")["items"][0]["review"]["lifecycle"])

    def test_failed_parity_or_an_unreadable_page_writes_no_plan(self) -> None:
        package = self.package()
        with self.assertRaisesRegex(ValueError, "parity failed"):
            self.plan(package, independent=self.independent([MASTHEAD, ["entirely different words here"]]))
        self.assertFalse((self.out / "plan.json").exists())
        self.assertEqual(read_json(self.out / "extraction-report.json")["parity"]["pages_below_minimum"], [2])
        with self.assertRaisesRegex(ValueError, "parity failed"):
            self.plan(package, Path(self.temp.name) / "pages", independent=self.independent([MASTHEAD]))
        with self.assertRaisesRegex(ValueError, r"no embedded text.*\[2\]"):
            self.plan(self.package([MASTHEAD, []], name="image-page.pdf"), Path(self.temp.name) / "ocr")

    def test_refuses_a_held_issue_a_tampered_source_and_any_library_write(self) -> None:
        package = self.package()
        with self.assertRaisesRegex(ValueError, "inside the library"):
            self.plan(package, self.library / "incoming")
        self.plan(package)
        with self.assertRaisesRegex(FileExistsError, "already has content"):
            self.plan(package)
        manifest = self.library / "ROBOT_READABLE_DIRECTORY/MANIFESTS/documents.jsonl"
        before = manifest.read_bytes()
        manifest.write_bytes(before.replace(b"dcsa-voi-2026-09-voi", b"dcsa-voi-2026-10-voi"))
        with self.assertRaisesRegex(ValueError, "already holds dcsa-voi-2026-10-voi"):
            self.plan(package, Path(self.temp.name) / "held")
        manifest.write_bytes(before)
        (self.quarantine / "261030_VOI_Newsletter.pdf").write_bytes(make_pdf([MASTHEAD]))
        with self.assertRaisesRegex(ValueError, "hash/size mismatch"):
            self.plan(package, Path(self.temp.name) / "tampered")
        with self.assertRaisesRegex(ValueError, "quarantined Librarian package"):
            self.plan(self.package(name="approved.pdf", approval_state="approved"), Path(self.temp.name) / "approved")

    def test_a_missing_parity_extractor_is_an_error_not_a_skipped_check(self) -> None:
        with patch.object(voi_intake.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "independent extractor"):
                voi_intake.pdftotext_pages()


if __name__ == "__main__":
    unittest.main()
