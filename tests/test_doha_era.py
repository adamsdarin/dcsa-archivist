"""DOHA eras follow the decision date, in every store, and cannot silently regress.

All decision texts here are synthetic; no real case is reproduced.
"""
from __future__ import annotations

import contextlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from dcsa_custodian import doha_release
from dcsa_custodian.audit import audit_library
from dcsa_custodian.common import iter_jsonl, sha256_file, write_json, write_jsonl
from dcsa_custodian.doha import append_cases
from dcsa_custodian.doha_era import classify
from dcsa_custodian.release import build_candidate, validate_candidate
import test_custodian


def hearing(case_id: str, date_line: str, body: str = "") -> str:
    return (f"DEFENSE OFFICE OF HEARINGS AND APPEALS\n   ISCR Case No. {case_id}\n   Appearances\n"
            f"   For Government: Synthetic Counsel\n   For Applicant: Pro se\n\n      {date_line}\n"
            f"   ______________\n      Decision\n   ______________\n\nSynthetic financial considerations text. {body}\n")


class ClassifyTests(unittest.TestCase):
    def test_era_follows_the_decision_date_not_the_case_number(self) -> None:
        self.assertEqual(classify(hearing("16-12345", "03/05/2018"), "16-12345")["sead4_era"], "post_sead4")
        self.assertEqual(classify(hearing("15-12345", "06/07/2017"), "15-12345")["sead4_era"], "pre_sead4")
        result = classify(hearing("15-12345", "June 8, 2017"), "15-12345")
        self.assertEqual((result["sead4_era"], result["decision_date"]), ("post_sead4", "2017-06-08"))

    def test_appeal_header_date_is_used(self) -> None:
        result = classify("CASENO: 16-12345.a1\n\nDATE: 12/29/2017\n\nSynthetic appeal.", "16-12345")
        self.assertEqual((result["sead4_era"], result["decision_date_basis"]), ("post_sead4", "header_date"))

    def test_date_before_the_docket_year_is_not_trusted(self) -> None:
        text = hearing("17-12345", "08/08/2016", "DOHA received the transcript (Tr.) on March 16, 2018.")
        result = classify(text, "17-12345")
        self.assertIsNone(result["decision_date"])
        self.assertEqual(result["sead4_era"], "post_sead4")
        self.assertTrue(any("docket year" in conflict for conflict in result["date_conflicts"]))

    def test_contradicted_date_without_a_decisive_bound_stays_undetermined(self) -> None:
        text = hearing("15-12345", "03/31/2017", "The case was assigned to me on April 7, 2017.")
        self.assertEqual(classify(text, "15-12345")["sead4_era"], "undetermined")

    def test_official_listing_year_bounds_an_unstated_date(self) -> None:
        text = hearing("15-12345", "15-12345")
        self.assertEqual(classify(text, "15-12345")["sead4_era"], "undetermined")
        self.assertEqual(classify(text, "15-12345", listing_title="2016 and Prior ISCR Hearing Decisions - 3")["sead4_era"], "pre_sead4")
        self.assertEqual(classify(text, "15-12345", listing_title="2019 ISCR Hearing Decisions")["sead4_era"], "post_sead4")

    def test_impossible_day_keeps_the_month_as_evidence(self) -> None:
        result = classify(hearing("16-12345", "03/32/2018"), "16-12345")
        self.assertEqual((result["sead4_era"], result["decision_date"]), ("post_sead4", None))

    def test_review_takes_precedence_and_must_agree_with_its_own_date(self) -> None:
        review = {"document_id": "x", "decision_date": "2018-01-23", "reviewed_by": "reviewer",
                  "reviewed_utc": "2026-09-22T00:00:00Z", "evidence": "second DATE header"}
        self.assertEqual(classify(hearing("15-12345", "01/23/2006"), "15-12345", review)["sead4_era"], "post_sead4")
        with self.assertRaises(ValueError):
            classify("", "15-12345", {**review, "sead4_era": "pre_sead4"})


class ReleaseTests(unittest.TestCase):
    """The old rule grouped by case number; a candidate must correct every store."""

    CASES = {  # document_id: (case_id, date line, extra text, group the old rule gave it)
        "late-2016-case": ("16-12345", "03/05/2018", "", "PRE_SEAD_4"),
        "day-before": ("15-11111", "06/07/2017", "", "PRE_SEAD_4"),
        "effective-day": ("15-22222", "06/08/2017", "", "PRE_SEAD_4"),
        "typo-header": ("17-33333", "08/08/2016", "DOHA received the transcript (Tr.) on March 16, 2018.", "POST_SEAD_4"),
    }

    def make_library(self, root: Path) -> None:
        test_custodian.CustodianTests().make_library(root)
        taxonomy = {"schema_version": "1.0", "guidelines": {"F": {"aliases": ["financial considerations"]}}}
        records = []
        for identity, (case_id, date_line, extra, group) in self.CASES.items():
            robot = f"ROBOT_READABLE_DIRECTORY/TEXT/PERSONNEL_VETTING/DOHA_DECISIONS/{group}/{identity}.txt"
            human = f"HUMAN_READABLE_DIRECTORY/PERSONNEL_VETTING/DOHA_DECISIONS/{group}/{identity}.pdf"
            (root / robot).parent.mkdir(parents=True, exist_ok=True)
            (root / human).parent.mkdir(parents=True, exist_ok=True)
            (root / robot).write_text(hearing(case_id, date_line, extra), encoding="utf-8")
            (root / human).write_bytes(b"%PDF-synthetic-" + identity.encode())
            records.append({"document_id": identity, "collection_id": "doha_decisions", "domain": "personnel_vetting",
                            "authority_tier": 5, "current_status": "historical_case_research",
                            "human_source_path": human, "robot_text_path": robot, "current_group": group, "doha_group": group,
                            "robot_sha256": sha256_file(root / robot),
                            "doha_review": {"case_id": case_id, "decision_level": "h1", "decision_date": "2018-01-01",
                                            "current_group": group, "outcome": "denied", "guidelines": ["F"],
                                            "answer_eligible": False, "reviewed_by": "synthetic", "reviewed_utc": "2026-09-22T00:00:00Z",
                                            "metadata_basis": "synthetic fixture"}})
        append_cases(root, records, taxonomy)
        manifest = root / "ROBOT_READABLE_DIRECTORY/MANIFESTS/documents.jsonl"
        base = [row for _, row in iter_jsonl(manifest)]
        write_jsonl(manifest, base + [{k: v for k, v in r.items() if k not in ("doha_review", "robot_sha256")} for r in records])
        write_json(root / doha_release.RULES, {"cutoff": "2017-07-31", "delineation_case": "synthetic"})

    def build(self, base: Path) -> tuple[Path, dict]:
        root, project = base / "library", base / "project"
        root.mkdir()
        (project / "evals").mkdir(parents=True)
        self.make_library(root)
        write_json(project / "evals/golden_queries.json", {"schema_version": "1.0", "cases": [{"id": "rule", "query": "contractor safeguarding requirement", "require_hit": True, "expected_first_role": "controlling_regulation"}]})
        config = {"state_directory": ".custodian", "default_chunk_characters": 100, "maximum_chunk_characters": 160, "chunk_overlap_characters": 10}
        return root, build_candidate(project, root, config, "doha-era-release")

    def test_candidate_corrects_every_store_and_leaves_the_library_alone(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root, result = self.build(Path(temp))
            self.assertTrue(result["validation"]["valid"], result["validation"]["errors"])
            production = Path(result["release_directory"]) / "production"
            eras = {row["document_id"]: row for _, row in iter_jsonl(production / doha_release.ERA_MANIFEST)}
            self.assertEqual({i: r["sead4_era"] for i, r in eras.items()},
                             {"late-2016-case": "post_sead4", "day-before": "pre_sead4",
                              "effective-day": "post_sead4", "typo-header": "post_sead4"})
            self.assertIsNone(eras["typo-header"]["decision_date"])
            self.assertIsNone(eras["late-2016-case"]["source_url"])
            with contextlib.closing(sqlite3.connect(production / doha_release.CONTENT)) as db:
                self.assertEqual(db.execute("SELECT current_group FROM decisions WHERE document_id='late-2016-case'").fetchone()[0], "POST_SEAD_4")
                self.assertEqual(db.execute("SELECT current_group FROM corpus WHERE document_id='late-2016-case'").fetchone()[0], "POST_SEAD_4")
            documents = {r["document_id"]: r for _, r in iter_jsonl(production / doha_release.DOCUMENTS)}
            self.assertEqual(documents["late-2016-case"]["doha_group"], "POST_SEAD_4")
            self.assertIn("/PRE_SEAD_4/", documents["late-2016-case"]["robot_text_path"], "paths never move")
            rules = json.loads((production / doha_release.RULES).read_text(encoding="utf-8"))
            self.assertEqual((rules["cutoff"], rules["superseded_rule"]["cutoff"]), ("2017-06-08", "2017-07-31"))
            with contextlib.closing(sqlite3.connect(root / doha_release.CONTENT)) as db:
                self.assertEqual(db.execute("SELECT current_group FROM decisions WHERE document_id='late-2016-case'").fetchone()[0], "PRE_SEAD_4")

    def test_validation_refuses_a_case_number_era_even_when_every_store_agrees(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root, result = self.build(Path(temp))
            production = Path(result["release_directory"]) / "production"
            # Reapply the old case-number grouping consistently to every copy.
            for relative in (doha_release.ERA_MANIFEST, doha_release.PATH_MANIFEST):
                rows = [row for _, row in iter_jsonl(production / relative)]
                for row in rows:
                    if row["document_id"] == "late-2016-case":
                        row.update(sead4_era="pre_sead4", current_group="PRE_SEAD_4", retrieval_priority=25, decision_date=None)
                write_jsonl(production / relative, rows)
            for relative, table, column in ((doha_release.CONTENT, "decisions", "retrieval_priority"),
                                            (doha_release.PATHS, "current_paths", "authority_priority")):
                with contextlib.closing(sqlite3.connect(production / relative)) as db, db:
                    db.execute(f"UPDATE {table} SET current_group='PRE_SEAD_4',{column}=25 WHERE document_id='late-2016-case'")
                    if table == "decisions":
                        db.execute("UPDATE corpus SET current_group='PRE_SEAD_4' WHERE document_id='late-2016-case'")
            documents = [row for _, row in iter_jsonl(production / doha_release.DOCUMENTS)]
            for row in documents:
                if row["document_id"] == "late-2016-case":
                    row.update(current_group="PRE_SEAD_4", doha_group="PRE_SEAD_4")
            write_jsonl(production / doha_release.DOCUMENTS, documents)
            errors = doha_release.check(production, root)
            self.assertTrue(any("decision-date classification" in error for error in errors), errors)
            self.assertFalse(any("disagrees" in error for error in errors), errors)

    def test_validation_refuses_stores_that_disagree(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root, result = self.build(Path(temp))
            release = Path(result["release_directory"])
            with contextlib.closing(sqlite3.connect(release / "production" / doha_release.CONTENT)) as db, db:
                db.execute("UPDATE decisions SET current_group='PRE_SEAD_4' WHERE document_id='effective-day'")
            errors = validate_candidate(root, release)["errors"]
            self.assertTrue(any("DOHA_CASE_TOPICS_FTS.sqlite disagrees" in error for error in errors), errors)

    def test_doctor_reports_an_uncorrected_library(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "library"
            root.mkdir()
            self.make_library(root)
            audit = audit_library(root)
            self.assertTrue(audit["summary"]["integrity_healthy"])
            self.assertGreater(audit["quality_blockers"]["doha_era_inconsistencies"], 0)


if __name__ == "__main__":
    unittest.main()
