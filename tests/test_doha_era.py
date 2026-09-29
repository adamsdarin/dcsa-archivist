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

    def test_the_decisions_own_date_line_wins_over_the_doha_index_header(self) -> None:
        # DOHA prepends KEYWORD/CASENO/DATE index lines; the decision's own date line follows.
        text = "CASENO: 15-12345.a1\nDATE: 07/11/2016\n  DATE: July 12, 2016\n\nSynthetic appeal."
        result = classify(text, "15-12345")
        self.assertEqual((result["decision_date"], result["decision_date_basis"]), ("2016-07-12", "header_date"))
        # An own line with an impossible date gives way to the index header.
        text = "CASENO: 08-12345.a1\nDATE: 04/03/2009\n  DATE: April 3, 3009\n\nSynthetic appeal."
        self.assertEqual(classify(text, "08-12345")["decision_date"], "2009-04-03")

    def test_date_before_the_docket_year_is_not_trusted(self) -> None:
        text = hearing("17-12345", "08/08/2016", "DOHA received the transcript (Tr.) on March 16, 2018.")
        result = classify(text, "17-12345")
        self.assertIsNone(result["decision_date"])
        self.assertEqual(result["sead4_era"], "post_sead4")
        self.assertTrue(any("docket year" in conflict for conflict in result["date_conflicts"]))

    def test_contradicted_date_without_a_decisive_bound_stays_undetermined(self) -> None:
        text = hearing("15-12345", "03/31/2017", "The case was assigned to me on April 7, 2017.")
        self.assertEqual(classify(text, "15-12345")["sead4_era"], "undetermined")

    def test_official_listing_year_bounds_an_unstated_date_from_above(self) -> None:
        text = hearing("15-12345", "15-12345")
        self.assertEqual(classify(text, "15-12345")["sead4_era"], "undetermined")
        self.assertEqual(classify(text, "15-12345", listing_title="2016 and Prior ISCR Hearing Decisions - 3")["sead4_era"], "pre_sead4")
        # DOHA posts late, so the listing year is no lower bound: a 2019 listing
        # does not make an undated 2015 case post-SEAD 4.
        self.assertEqual(classify(text, "15-12345", listing_title="2019 ISCR Hearing Decisions")["sead4_era"], "undetermined")

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

    def make_library(self, root: Path, crlf: tuple[str, ...] = (), keep_hashes: bool = False) -> None:
        """DOHA texts are LF on every platform, except those named in ``crlf``."""
        test_custodian.CustodianTests().make_library(root)
        taxonomy = {"schema_version": "1.0", "guidelines": {"F": {"aliases": ["financial considerations"]}}}
        records = []
        for identity, (case_id, date_line, extra, group) in self.CASES.items():
            robot = f"ROBOT_READABLE_DIRECTORY/TEXT/PERSONNEL_VETTING/DOHA_DECISIONS/{group}/{identity}.txt"
            human = f"HUMAN_READABLE_DIRECTORY/PERSONNEL_VETTING/DOHA_DECISIONS/{group}/{identity}.pdf"
            (root / robot).parent.mkdir(parents=True, exist_ok=True)
            (root / human).parent.mkdir(parents=True, exist_ok=True)
            text = hearing(case_id, date_line, extra)
            (root / robot).write_bytes((text.replace("\n", "\r\n") if identity in crlf else text).encode("utf-8"))
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
        dropped = ("doha_review",) if keep_hashes else ("doha_review", "robot_sha256")
        write_jsonl(manifest, base + [{k: v for k, v in r.items() if k not in dropped} for r in records])
        write_json(root / doha_release.RULES, {"cutoff": "2017-07-31", "delineation_case": "synthetic"})

    def build(self, base: Path, crlf: tuple[str, ...] = (), line_endings: bool = False) -> tuple[Path, dict]:
        root, project = base / "library", base / "project"
        root.mkdir()
        (project / "evals").mkdir(parents=True)
        self.make_library(root, crlf, keep_hashes=bool(crlf))
        if line_endings:
            write_jsonl(project / "decisions/doha_robot_line_endings.jsonl", doha_release.plan_line_endings(root)[0])
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

    def test_only_decisions_whose_era_changes_are_rewritten_in_the_topic_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "library"
            root.mkdir()
            self.make_library(root)
            production = Path(temp) / "production"
            report = doha_release.build(root, production, {}, {})
            # late-2016-case and effective-day move to post-SEAD 4; the others were staged in the right era.
            self.assertEqual(report["rewritten"]["topic_index_rows"], 2)
            self.assertEqual(doha_release.check(production, root), [])

    def test_decisions_staged_in_the_right_era_leave_the_topic_index_out_of_the_candidate(self) -> None:
        self.CASES = {k: v for k, v in ReleaseTests.CASES.items() if k in ("day-before", "typo-header")}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "library"
            root.mkdir()
            self.make_library(root)
            production = Path(temp) / "production"
            report = doha_release.build(root, production, {}, {})
            self.assertEqual((report["rewritten"]["path_index_rows"], report["rewritten"]["topic_index_rows"]), (0, 0))
            self.assertFalse((production / doha_release.CONTENT).exists())
            self.assertEqual(doha_release.check(production, root), [])

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

    def phantom(self, root: Path, survivor: str = "late-2016-case") -> dict:
        """A row naming files the library does not hold, with a real row's indexed text."""
        rows = [row for _, row in iter_jsonl(root / doha_release.PATH_MANIFEST)]
        real = next(row for row in rows if row["document_id"] == survivor)
        ghost = dict(real, document_id="ghost", case_stem="16-12345.h1",
                     robot_text_path="ROBOT_READABLE_DIRECTORY/TEXT/PERSONNEL_VETTING/DOHA_DECISIONS/PRE_SEAD_4/ghost.txt",
                     human_source_path="HUMAN_READABLE_DIRECTORY/PERSONNEL_VETTING/DOHA_DECISIONS/PRE_SEAD_4/ghost.pdf")
        write_jsonl(root / doha_release.PATH_MANIFEST, rows + [ghost])
        with contextlib.closing(sqlite3.connect(root / doha_release.CONTENT)) as db, db:
            for table in ("decisions", "corpus"):
                columns = [r[1] for r in db.execute(f"PRAGMA table_info({table})")] if table == "decisions" else None
                if columns:
                    values = dict(zip(columns, db.execute("SELECT * FROM decisions WHERE document_id=?", (survivor,)).fetchone()))
                    values["document_id"] = "ghost"
                    db.execute(f"INSERT INTO decisions({','.join(values)}) VALUES({','.join('?' * len(values))})", tuple(values.values()))
                else:
                    content = db.execute("SELECT content FROM corpus WHERE document_id=?", (survivor,)).fetchone()[0]
                    db.execute("INSERT INTO corpus(document_id,content) VALUES(?,?)", ("ghost", content))
        with contextlib.closing(sqlite3.connect(root / doha_release.PATHS)) as db, db:
            db.execute("INSERT INTO current_paths(document_id,case_stem,current_group,human_source_path,robot_text_path,authority_priority)"
                       " VALUES('ghost','16-12345.h1','PRE_SEAD_4',?,?,25)", (ghost["human_source_path"], ghost["robot_text_path"]))
        return {"document_id": "ghost", "superseded_by": f"{survivor}", "reviewed_by": "reviewer",
                "reviewed_utc": "2026-09-23T00:00:00Z", "evidence": "no artifacts; identical indexed text"}

    def test_a_row_without_robot_text_fails_validation_until_it_is_retired(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "library"
            root.mkdir()
            self.make_library(root)
            retirement = self.phantom(root)
            production = Path(temp) / "production"
            doha_release.build(root, production, {}, {})
            self.assertTrue(any("robot text the library does not hold" in error
                                for error in doha_release.check(production, root)), "a dead path must block a release")
            retirements = {"ghost": retirement}
            report = doha_release.build(root, production, {}, {}, retirements)
            self.assertEqual([item["document_id"] for item in report["retired"]], ["ghost"])
            self.assertEqual(doha_release.check(production, root, retirements=retirements), [])
            eras = {row["document_id"] for _, row in iter_jsonl(production / doha_release.ERA_MANIFEST)}
            self.assertNotIn("ghost", eras)
            with contextlib.closing(sqlite3.connect(production / doha_release.CONTENT)) as db:
                for table in ("decisions", "corpus"):
                    self.assertIsNone(db.execute(f"SELECT 1 FROM {table} WHERE document_id='ghost'").fetchone())
            with contextlib.closing(sqlite3.connect(production / doha_release.PATHS)) as db:
                self.assertIsNone(db.execute("SELECT 1 FROM current_paths WHERE document_id='ghost'").fetchone())

    def test_a_published_retirement_does_not_block_later_builds(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "library"
            root.mkdir()
            # The library this retirement was published into no longer holds the row.
            self.make_library(root)
            retirement = {"document_id": "ghost", "superseded_by": "late-2016-case", "reviewed_by": "reviewer",
                          "reviewed_utc": "2026-09-23T00:00:00Z", "evidence": "no artifacts; identical indexed text"}
            production = Path(temp) / "production"
            report = doha_release.build(root, production, {}, {}, {"ghost": retirement})
            self.assertEqual(report["retired"], [])
            self.assertEqual([item["document_id"] for item in report["already_retired"]], ["ghost"])
            self.assertEqual(doha_release.check(production, root, retirements={"ghost": retirement}), [])
            # An absent row whose survivor is gone too is still refused.
            with self.assertRaises(ValueError):
                doha_release.build(root, production, {}, {}, {"ghost": dict(retirement, superseded_by="no-such-row")})

    def test_retirement_is_refused_when_the_library_still_holds_the_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "library"
            root.mkdir()
            self.make_library(root)
            retirement = self.phantom(root)
            production = Path(temp) / "production"
            # A real row, with files on disk, can never be retired.
            with self.assertRaises(ValueError):
                doha_release.build(root, production, {}, {}, {"late-2016-case": dict(retirement, document_id="late-2016-case", superseded_by="day-before")})
            # Nor a phantom whose indexed text differs from the row said to supersede it.
            with self.assertRaises(ValueError):
                doha_release.build(root, production, {}, {}, {"ghost": dict(retirement, superseded_by="day-before")})
            # Nor one the source manifest still carries.
            documents = [record for _, record in iter_jsonl(root / doha_release.DOCUMENTS)]
            write_jsonl(root / doha_release.DOCUMENTS, documents + [{"document_id": "ghost", "collection_id": "doha_decisions"}])
            with self.assertRaises(ValueError):
                doha_release.build(root, production, {}, {}, {"ghost": retirement})

    def test_doctor_reports_an_uncorrected_library(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "library"
            root.mkdir()
            self.make_library(root)
            audit = audit_library(root)
            self.assertTrue(audit["summary"]["integrity_healthy"])
            self.assertGreater(audit["quality_blockers"]["doha_era_inconsistencies"], 0)


class LineEndingTests(unittest.TestCase):
    """CRLF robot texts become LF by reviewed rows, with every store that hashes them, and never return."""

    CRLF = ("late-2016-case", "day-before")

    def stores(self, base: Path) -> dict[str, dict[str, object]]:
        """Each decision's hash as the documents manifest, the topic index and the enriched manifest record it."""
        with contextlib.closing(sqlite3.connect(base / doha_release.CONTENT)) as db:
            index = {i: (h, n) for i, h, n in db.execute("SELECT document_id,content_sha256,content_bytes FROM decisions")}
        documents = {r["document_id"]: r.get("robot_sha256") for _, r in iter_jsonl(base / doha_release.DOCUMENTS)
                     if r.get("collection_id") == "doha_decisions"}
        return {"index": index, "documents": documents}

    def test_reviewed_rows_rewrite_the_text_and_every_hash_and_nothing_else(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root, result = ReleaseTests().build(Path(temp), crlf=self.CRLF, line_endings=True)
            self.assertTrue(result["validation"]["valid"], result["validation"]["errors"])
            release = Path(result["release_directory"])
            production = release / "production"
            report = json.loads((release / "reports/DOHA_ERA_REPORT.json").read_text(encoding="utf-8"))
            self.assertEqual((report["line_endings"]["rewritten"], report["rewritten"]["robot_texts"]), (2, 2))
            before, after = self.stores(root), self.stores(production)
            enriched = {r["document_id"]: r["robot_content_sha256"] for _, r in
                        iter_jsonl(production / "ROBOT_READABLE_DIRECTORY/MANIFESTS/DOCUMENTS_ENRICHED.jsonl")
                        if r.get("collection_id") == "doha_decisions"}
            for identity, (case_id, date_line, extra, group) in ReleaseTests.CASES.items():
                relative = f"ROBOT_READABLE_DIRECTORY/TEXT/PERSONNEL_VETTING/DOHA_DECISIONS/{group}/{identity}.txt"
                live = (root / relative).read_bytes()
                if identity in self.CRLF:
                    staged = (production / relative).read_bytes()
                    self.assertEqual(staged, hearing(case_id, date_line, extra).encode("utf-8"))
                    self.assertIn(b"\r\n", live, "the live library is only read")
                    digest = (sha256_file(production / relative), len(staged))
                    self.assertEqual((after["index"][identity], after["documents"][identity], enriched[identity]),
                                     (digest, digest[0], digest[0]))
                    self.assertNotEqual(before["index"][identity], digest)
                else:
                    self.assertFalse((production / relative).exists(), "an LF text is not rewritten")
                    self.assertEqual(after["index"][identity], before["index"][identity])
            with contextlib.closing(sqlite3.connect(production / doha_release.CONTENT)) as db:
                content = db.execute("SELECT content FROM corpus WHERE document_id='late-2016-case'").fetchone()[0]
            self.assertEqual(content, hearing("16-12345", "03/05/2018"), "the indexed text never had CR in it")
            eras = {r["document_id"]: (r["sead4_era"], r["decision_date"]) for _, r in iter_jsonl(production / doha_release.ERA_MANIFEST)}
            self.assertEqual(eras["late-2016-case"], ("post_sead4", "2018-03-05"))

    def test_a_crlf_text_or_a_hash_that_does_not_bind_the_file_fails_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root, result = ReleaseTests().build(Path(temp), crlf=self.CRLF)
            errors = result["validation"]["errors"]
            self.assertTrue(any("CR line ends" in error and "2 decisions" in error for error in errors), errors)
        with tempfile.TemporaryDirectory() as temp:
            root, result = ReleaseTests().build(Path(temp), crlf=self.CRLF, line_endings=True)
            release = Path(result["release_directory"])
            with contextlib.closing(sqlite3.connect(release / "production" / doha_release.CONTENT)) as db, db:
                db.execute("UPDATE decisions SET content_bytes=content_bytes+1 WHERE document_id='day-before'")
            errors = doha_release.check_texts(release / "production", root)
            self.assertEqual(len(errors), 1, errors)
            self.assertIn("content_sha256/content_bytes differ", errors[0])

    def test_a_text_that_is_not_as_reviewed_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "library"
            root.mkdir()
            ReleaseTests().make_library(root, crlf=self.CRLF, keep_hashes=True)
            rows = {row["document_id"]: row for row in doha_release.plan_line_endings(root)[0]}
            production = Path(temp) / "production"
            text = root / rows["day-before"]["robot_text_path"]
            text.write_bytes(text.read_bytes() + b"edited after review\r\n")
            with self.assertRaisesRegex(ValueError, "changed since its line-ending review"):
                doha_release.build(root, production, {}, {}, line_endings=rows)
            # A lone CR or LF is not the rule's to settle.
            text.write_bytes(b"line one\r\nline two\n")
            planned, summary = doha_release.plan_line_endings(root)
            self.assertEqual([item["document_id"] for item in summary["refused"]], ["day-before"])
            self.assertNotIn("day-before", {row["document_id"] for row in planned})

    def test_published_rows_are_already_applied_in_later_builds(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            crlf_root = base / "before"
            crlf_root.mkdir()
            ReleaseTests().make_library(crlf_root, crlf=self.CRLF, keep_hashes=True)
            rows = {row["document_id"]: row for row in doha_release.plan_line_endings(crlf_root)[0]}
            # The library as published: LF texts, and every store carrying the LF hash.
            root = base / "library"
            root.mkdir()
            ReleaseTests().make_library(root, keep_hashes=True)
            production = base / "production"
            report = doha_release.build(root, production, {}, {}, line_endings=rows)
            self.assertEqual((report["line_endings"]["rewritten"], report["line_endings"]["already_applied"]), (0, 2))
            self.assertEqual(doha_release.check_texts(production, root), [])
            documents = [r for _, r in iter_jsonl(production / doha_release.DOCUMENTS)] \
                if (production / doha_release.DOCUMENTS).exists() else [r for _, r in iter_jsonl(root / doha_release.DOCUMENTS)]
            self.assertEqual({r["document_id"]: r.get("robot_sha256") for r in documents if r["document_id"] in rows},
                             {identity: row["after_sha256"] for identity, row in rows.items()})


if __name__ == "__main__":
    unittest.main()
