"""Batches keep cases together; samples are seeded and proportional; scores state a bound; the
re-check finds where held decisions and the rules disagree. All decisions here are synthetic."""
from __future__ import annotations

import csv
import math
from pathlib import Path
import unittest

from dcsa_custodian.common import iter_jsonl, read_json, sha256_file, write_jsonl
from dcsa_custodian.doha import append_cases
from dcsa_custodian.doha_quality import (accuracy_sample, allocate, append_provenance, recheck_library,
                                         score_sheet, split_plan, upper_bound)
from dcsa_custodian.intake import stage_intake

try:
    from tests import test_doha_bulk as bulk
except ImportError:  # run from inside tests/
    import test_doha_bulk as bulk

HEARING_TEXT = bulk.hearing("19-01234", "h1", "01/15/2020", "Guideline F",
                            "National security eligibility for access to classified information is denied.")
APPEAL_TEXT = bulk.appeal("19-01234", "06/01/2020", "Guideline F",
                          "The Judge's adverse security clearance decision is AFFIRMED.")


class QualityTests(unittest.TestCase):
    setUp = bulk.DohaBulkTests.setUp
    add = bulk.DohaBulkTests.add
    extract = bulk.DohaBulkTests.extract
    build = bulk.DohaBulkTests.build

    def plan(self) -> Path:
        self.add("19-01234.a1", APPEAL_TEXT)
        self.assertEqual(self.build()["counts"]["planned"], 4)
        return self.out

    def sheet(self, name: str) -> Path:
        return self.out.parent / name

    # ---------------------------------------------------------------- batches

    def test_batches_keep_a_case_together_and_each_is_stageable(self) -> None:
        plan = self.plan()
        report = split_plan(plan, 1, self.out.parent / "batches")
        self.assertEqual(sum(b["decisions"] for b in report["batches"]), 4)
        by_case: dict[str, set[str]] = {}
        for entry in report["batches"]:
            batch = self.out.parent / "batches" / entry["batch"]
            items = read_json(batch / "intake-plan.json")["items"]
            for item in items:
                by_case.setdefault(item["record"]["doha_review"]["case_id"], set()).add(entry["batch"])
                self.assertEqual(sha256_file(batch / item["robot_file"]), item["robot_sha256"])
            rows = [row["document_id"] for _, row in iter_jsonl(batch / "doha_source_urls.additions.jsonl")]
            self.assertEqual(sorted(rows), sorted(i["record"]["document_id"] for i in items))
            stage_intake(self.library, self.out.parent / f"staged-{entry['batch']}", batch / "intake-plan.json")
        self.assertEqual(len(by_case["19-01234"]), 1, "an appeal and the hearing it reviewed share a batch")
        self.assertEqual(len(report["batches"]), 3)

    def test_batches_refuse_an_existing_output(self) -> None:
        plan = self.plan()
        (self.out.parent / "batches").mkdir()
        with self.assertRaises(FileExistsError):
            split_plan(plan, 10, self.out.parent / "batches")

    # ---------------------------------------------------------------- sampling

    def test_allocation_is_proportional(self) -> None:
        self.assertEqual(allocate({"a": 90, "b": 10}, 10), {"a": 9, "b": 1})
        self.assertEqual(sum(allocate({"a": 5, "b": 5, "c": 5}, 7).values()), 7)
        self.assertEqual(allocate({"a": 2}, 10), {"a": 2})

    def test_the_sample_is_seeded_and_points_at_the_pdfs(self) -> None:
        plan = self.plan()
        first = accuracy_sample(plan, self.sheet("a.csv"), size=4, edge=0, seed=7)
        accuracy_sample(plan, self.sheet("b.csv"), size=4, edge=0, seed=7)
        self.assertEqual(self.sheet("a.csv").read_bytes(), self.sheet("b.csv").read_bytes())
        self.assertEqual(first["estimate"], 4)
        with self.sheet("a.csv").open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertTrue(all(Path(row["pdf"]).is_file() for row in rows))
        appeal, = [row for row in rows if row["case_key"] == "19-01234.a1"]
        self.assertEqual((appeal["appeal_disposition"], appeal["reviewed_decision"]), ("affirmed", "19-01234.h1 (denied)"))
        with self.assertRaises(FileExistsError):
            accuracy_sample(plan, self.sheet("a.csv"))

    # ---------------------------------------------------------------- scoring

    def test_upper_bound_matches_the_closed_form(self) -> None:
        self.assertAlmostEqual(upper_bound(0, 150), 1 - 0.05 ** (1 / 150), places=4)
        self.assertTrue(0.040 < upper_bound(2, 150) < 0.042)
        self.assertEqual(upper_bound(0, 0), 1.0)

    def write_marks(self, name: str, rows: list[dict[str, str]]) -> Path:
        path = self.sheet(name)
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        return path

    def marks(self, n: int, wrong: int, purpose: str = "estimate") -> list[dict[str, str]]:
        return [{"sample_id": str(i), "purpose": purpose, "case_key": f"20-{i:05d}.h1", "appeal_disposition": "",
                 "date_ok": "Y", "outcome_ok": "N" if i < wrong else "Y", "appeal_ok": "", "topics_ok": "y",
                 "notes": ""} for i in range(n)]

    def test_a_sheet_passes_only_when_the_bound_is_under_target(self) -> None:
        good = score_sheet(self.write_marks("good.csv", self.marks(150, 2)), 0.05)
        self.assertTrue(good["passed"])
        self.assertEqual((good["decisions_scored"], good["decisions_wrong"]), (150, 2))
        bad = score_sheet(self.write_marks("bad.csv", self.marks(150, 4)), 0.05)
        self.assertFalse(bad["passed"])
        self.assertEqual(bad["wrong"][0]["wrong"], ["outcome"])

    def test_edge_rows_are_reported_but_not_scored(self) -> None:
        rows = self.marks(20, 0) + [dict(r, sample_id=str(100 + i)) for i, r in enumerate(self.marks(3, 3, "edge"))]
        result = score_sheet(self.write_marks("edge.csv", rows), 0.5)
        self.assertEqual((result["decisions_scored"], result["decisions_wrong"]), (20, 0))
        self.assertEqual(len(result["edge_rows_wrong"]), 3)

    def test_an_unchecked_row_refuses_to_score(self) -> None:
        rows = self.marks(3, 0)
        rows[1]["date_ok"] = ""
        with self.assertRaisesRegex(ValueError, "date_ok"):
            score_sheet(self.write_marks("blank.csv", rows), 0.05)

    # ---------------------------------------------------------------- held library

    def hold(self, key: str, text: str, date_: str, outcome_: str, guidelines: list[str]) -> None:
        case_id, level = key.split(".")
        stem = f"{key}_{outcome_}" + "".join(f"_{g}" for g in guidelines)
        robot = self.library / f"ROBOT_READABLE_DIRECTORY/TEXT/PERSONNEL_VETTING/DOHA_DECISIONS/POST_SEAD_4/{stem}.txt"
        robot.write_text(text, encoding="utf-8")
        append_cases(self.library, [{
            "document_id": f"held-{key}", "collection_id": "doha_decisions", "authority_tier": 5,
            "current_status": "historical_case_research",
            "human_source_path": f"HUMAN_READABLE_DIRECTORY/PERSONNEL_VETTING/DOHA_DECISIONS/POST_SEAD_4/{stem}.pdf",
            "robot_text_path": robot.relative_to(self.library).as_posix(), "robot_sha256": sha256_file(robot),
            "doha_review": {"case_id": case_id, "decision_level": level, "decision_date": date_,
                            "current_group": "POST_SEAD_4", "outcome": outcome_, "guidelines": guidelines,
                            "answer_eligible": False, "reviewed_by": "synthetic",
                            "reviewed_utc": "2026-09-01T00:00:00Z", "metadata_basis": "synthetic"}}], bulk.TAXONOMY_BODY)

    def test_recheck_lists_disagreements_and_proposes_appeal_fields(self) -> None:
        self.hold("19-01234.h1", HEARING_TEXT, "2020-01-15", "denied", ["F"])
        self.hold("19-01234.a1", APPEAL_TEXT, "2020-06-01", "approved", ["B"])  # stored wrong on purpose
        before = sha256_file(self.library / "LOCAL_INDEXES/DOHA_CASE_TOPICS_FTS.sqlite")
        out = self.out.parent / "recheck"
        summary = recheck_library(self.library, out, sample_size=2, edge=0)
        found = {(r["case_key"], r["field"]): r for _, r in iter_jsonl(out / "disagreements.jsonl")}
        self.assertEqual(found[("19-01234.a1", "outcome")]["rule_value"], "denied")
        self.assertEqual(found[("19-01234.a1", "topics")]["rule_value"], "F")
        self.assertNotIn(("19-01234.h1", "outcome"), found)
        backfill = {r["case_key"]: r for _, r in iter_jsonl(out / "ruling_backfill.jsonl")}
        self.assertEqual(backfill["19-01234.a1"]["appeal_disposition"], "affirmed")
        self.assertEqual(backfill["19-01234.a1"]["appealed_by"], "Applicant")
        self.assertEqual(backfill["19-01234.a1"]["reviewed_decision"]["case_key"], "19-01234.h1")
        self.assertEqual(backfill["19-01234.a1"]["reviewed_decision"]["status"], "held by the library")
        unsettled = {(r["case_key"], r["field"]) for _, r in iter_jsonl(out / "unsettled.jsonl")}
        self.assertIn(("18-00005.h1", "outcome"), unsettled, "the placeholder text states no outcome")
        self.assertEqual(summary["counts"]["decisions"], 3)
        self.assertTrue((out / "disagreements_sample.csv").is_file())
        self.assertTrue((out / "existing_accuracy_sample.csv").is_file())
        self.assertEqual(sha256_file(self.library / "LOCAL_INDEXES/DOHA_CASE_TOPICS_FTS.sqlite"), before,
                         "the re-check must not write the library")

    def test_legacy_space_separated_topics_and_missing_outcomes(self) -> None:
        text = bulk.hearing("19-07777", "h1", "01/15/2020", "Foreign Influence; Delinquent debt",
                            "Eligibility for access to classified information is denied.")
        self.hold("19-07777.h1", text, "2020-01-15", "denied", ["B", "F"])
        self.hold("19-01234.a1", APPEAL_TEXT, "2020-06-01", "denied", ["F"])
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(self.library / "LOCAL_INDEXES/DOHA_CASE_TOPICS_FTS.sqlite")) as db, db:
            db.execute("UPDATE decisions SET guideline_codes='B F' WHERE document_id='held-19-07777.h1'")
            db.execute("UPDATE decisions SET outcome=NULL WHERE document_id='held-19-01234.a1'")
        out = self.out.parent / "recheck-legacy"
        recheck_library(self.library, out, sample_size=1, edge=0)
        found = {(r["case_key"], r["field"]): r for _, r in iter_jsonl(out / "disagreements.jsonl")}
        self.assertNotIn(("19-07777.h1", "topics"), found, "'B F' and B,F are the same topics")
        self.assertEqual(found[("19-01234.a1", "outcome_missing")]["rule_value"], "denied")
        self.assertNotIn(("19-01234.a1", "outcome"), found)

    def test_a_checked_disagreement_sheet_is_tallied(self) -> None:
        rows = [{"sample_id": "1", "case_key": "x.a1", "field": "outcome", "verdict": "rule"},
                {"sample_id": "2", "case_key": "y.h1", "field": "outcome", "verdict": "Library"},
                {"sample_id": "3", "case_key": "z.h1", "field": "topics", "verdict": "neither"}]
        result = score_sheet(self.write_marks("dis.csv", rows), 0.05)
        self.assertEqual(result["by_field"], {"outcome": {"rule": 1, "library": 1}, "topics": {"neither": 1}})
        rows[0]["verdict"] = ""
        with self.assertRaises(ValueError):
            score_sheet(self.write_marks("dis2.csv", rows), 0.05)

    # ---------------------------------------------------------------- provenance

    def test_provenance_appends_once_and_refuses_conflicts(self) -> None:
        target = self.out.parent / "doha_source_urls.jsonl"
        write_jsonl(target, [{"document_id": "old", "source_url": "u0"}])
        additions = self.out.parent / "additions.jsonl"
        write_jsonl(additions, [{"document_id": "new", "source_url": "u1"}])
        self.assertEqual(append_provenance(additions, target)["added"], 1)
        again = append_provenance(additions, target)
        self.assertEqual((again["added"], again["already_recorded"]), (0, 1))
        self.assertEqual([r["document_id"] for _, r in iter_jsonl(target)], ["old", "new"])
        write_jsonl(additions, [{"document_id": "new", "source_url": "different"}])
        with self.assertRaisesRegex(ValueError, "different provenance"):
            append_provenance(additions, target)
        self.assertTrue(math.isclose(len(list(iter_jsonl(target))), 2))


if __name__ == "__main__":
    unittest.main()
