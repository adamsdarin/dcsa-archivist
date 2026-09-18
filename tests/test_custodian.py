from __future__ import annotations

import contextlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from dcsa_custodian.audit import audit_library
from dcsa_custodian.authority import classify_authority
from dcsa_custodian.chunks import build_chunks
from dcsa_custodian.common import sha256_file, write_json, write_jsonl
from dcsa_custodian.decisions import apply_metadata_decisions
from dcsa_custodian.directive_splits import DIRECTIVE_DOC_IDS, SPLIT_FOLDERS, build_directive_splits
from dcsa_custodian.enrich import enrich_manifest
from dcsa_custodian.release import build_candidate, validate_candidate
from dcsa_custodian.semantic import semantic_search


class CustodianTests(unittest.TestCase):
    def make_library(self, root: Path) -> None:
        robot = root / "ROBOT_READABLE_DIRECTORY/TEXT/AUTHORITIES/CFR/rule.txt"
        human = root / "HUMAN_READABLE_DIRECTORY/AUTHORITIES/CFR/rule.pdf"
        robot.parent.mkdir(parents=True)
        human.parent.mkdir(parents=True)
        robot.write_text("TIER: 1\nSTATUS: current\nDOC TYPE: regulation\n\nContractor safeguarding requirement.\fSecond page requirement.", encoding="utf-8")
        human.write_bytes(b"%PDF-test")
        records = [{
            "document_id": "rule", "collection_id": "cfr", "domain": "authorities",
            "human_source_path": "HUMAN_READABLE_DIRECTORY/AUTHORITIES/CFR/rule.pdf",
            "robot_text_path": "ROBOT_READABLE_DIRECTORY/TEXT/AUTHORITIES/CFR/rule.txt",
            "authority_tier": 1, "current_status": "current", "text_quality": "test",
        }]
        manifests = root / "ROBOT_READABLE_DIRECTORY/MANIFESTS"
        write_jsonl(manifests / "documents.jsonl", records)
        write_jsonl(manifests / "relationships.jsonl", [{
            "relation": "machine_readable_representation_of", **{key: records[0][key] for key in ("document_id", "human_source_path", "robot_text_path")}
        }])
        index = root / "LOCAL_INDEXES/DCSA_GENERAL_FTS.sqlite"
        index.parent.mkdir(parents=True)
        with contextlib.closing(sqlite3.connect(index)) as conn:
            conn.execute("CREATE VIRTUAL TABLE corpus USING fts5(document_id UNINDEXED, human_source_path UNINDEXED, robot_text_path UNINDEXED, content)")
            conn.execute("INSERT INTO corpus VALUES(?,?,?,?)", ("rule", records[0]["human_source_path"], records[0]["robot_text_path"], robot.read_text(encoding="utf-8")))
            conn.commit()
        write_json(root / "START_HERE_FOR_ROBOTS.json", {
            "documents": "ROBOT_READABLE_DIRECTORY/MANIFESTS/documents.jsonl",
            "relationships": "ROBOT_READABLE_DIRECTORY/MANIFESTS/relationships.jsonl",
            "local_indexes": ["LOCAL_INDEXES/DCSA_GENERAL_FTS.sqlite"],
        })

    def test_authority_classification(self) -> None:
        role, binding = classify_authority({"collection_id": "cfr", "current_status": "current"}, {"document_type_header": "regulation"})
        self.assertEqual(role, "controlling_regulation")
        self.assertIn("binding", binding)
        role, binding = classify_authority({"collection_id": "executive_orders", "current_status": "current"}, {"document_type_header": "executive order"})
        self.assertEqual(role, "executive_order")
        self.assertIn("not_automatically_contractor_binding", binding)
        role, binding = classify_authority({"collection_id": "cdse_resources", "current_status": "current_or_verify"}, {})
        self.assertEqual(role, "training_or_context")
        self.assertEqual(binding, "not_independently_binding")

    def test_chunks_are_verbatim_and_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_library(root)
            record = {
                "document_id": "rule", "canonical_document_id": "rule", "collection_id": "cfr", "domain": "authorities",
                "title": "Rule", "authority_role": "controlling_regulation", "authority_priority": 10,
                "authority_tier": 1, "current_status": "current", "answer_eligibility": "answer_eligible",
                "contractor_binding": "generally_binding_with_scope_checks",
                "human_source_path": "HUMAN_READABLE_DIRECTORY/AUTHORITIES/CFR/rule.pdf",
                "robot_text_path": "ROBOT_READABLE_DIRECTORY/TEXT/AUTHORITIES/CFR/rule.txt", "duplicate_of": None,
            }
            source = (root / record["robot_text_path"]).read_text(encoding="utf-8")
            chunks = build_chunks(root, [record], 30, 50, 5)
            self.assertTrue(chunks)
            self.assertTrue(all(chunk["content"] in source for chunk in chunks))
            self.assertTrue(all(len(chunk["content"]) <= 50 for chunk in chunks))

    def test_currency_decision_requires_evidence_and_promotes_only_exact_identity(self) -> None:
        record = {
            "source_document_id": "rule",
            "document_id": "rule",
            "collection_id": "cfr",
            "robot_text_path": "ROBOT_READABLE_DIRECTORY/TEXT/AUTHORITIES/CFR/rule.txt",
            "authority_role": "controlling_regulation",
            "current_status": "current_or_verify",
            "answer_eligibility": "unresolved_currency",
        }
        decision = {
            "source_document_id": "rule",
            "robot_text_path": record["robot_text_path"],
            "decision": "verified_current",
            "verified_utc": "2026-08-28T00:00:00Z",
            "verified_by": "test",
            "evidence": [{"url": "https://example.gov/rule"}],
            "note": "test evidence",
        }
        self.assertEqual(apply_metadata_decisions([record], [decision]), 1)
        self.assertEqual(record["answer_eligibility"], "answer_eligible")

    def _duplicate_pair(self) -> list[dict]:
        # Byte-identical copies as enrich_manifest leaves them: the copy filed under a
        # higher-authority folder won canonical, the correctly named one did not.
        winner = {"document_id": "form-mislabelled", "source_document_id": "form-mislabelled",
                  "robot_text_path": "TEXT/FOCI/Form January 2026.txt", "collection_id": "forms",
                  "authority_role": "dcsa_form", "title": "Form January 2026",
                  "answer_eligibility": "unresolved_currency", "duplicate_of": None,
                  "canonical_document_id": "form-mislabelled"}
        loser = {"document_id": "form-dec1999", "source_document_id": "form-dec1999",
                 "robot_text_path": "TEXT/FORMS/Expired/Form DEC 1999.txt", "collection_id": "forms",
                 "authority_role": "dcsa_form", "title": "Form DEC 1999",
                 "answer_eligibility": "excluded_duplicate", "duplicate_of": "form-mislabelled",
                 "canonical_document_id": "form-mislabelled"}
        return [winner, loser]

    def _decision(self, record: dict, **extra) -> dict:
        return {"source_document_id": record["source_document_id"], "robot_text_path": record["robot_text_path"],
                "decision": "historical", "verified_utc": "2026-09-18T00:00:00Z", "verified_by": "test",
                "evidence": [{"url": "https://example.gov/form"}], "note": "test", **extra}

    def test_reviewed_canonical_choice_overrides_folder_priority(self) -> None:
        winner, loser = records = self._duplicate_pair()
        apply_metadata_decisions(records, [self._decision(winner), self._decision(loser, canonical=True)])
        self.assertIsNone(loser["duplicate_of"])
        self.assertEqual(loser["answer_eligibility"], "historical_only")
        self.assertEqual(winner["duplicate_of"], "form-dec1999")
        self.assertEqual(winner["answer_eligibility"], "excluded_duplicate")
        self.assertEqual({r["canonical_document_id"] for r in records}, {"form-dec1999"})

    def test_canonical_choice_holds_whatever_the_decision_order(self) -> None:
        winner, loser = records = self._duplicate_pair()
        apply_metadata_decisions(records, [self._decision(loser, canonical=True), self._decision(winner)])
        self.assertEqual(winner["answer_eligibility"], "excluded_duplicate")
        self.assertEqual(loser["answer_eligibility"], "historical_only")

    def test_canonical_choice_needs_a_duplicate_group(self) -> None:
        winner, _ = self._duplicate_pair()
        winner["canonical_document_id"] = winner["document_id"]
        with self.assertRaisesRegex(ValueError, "no duplicate group"):
            apply_metadata_decisions([winner], [self._decision(winner, canonical=True)])

    def test_title_override_keeps_paths_and_source_title(self) -> None:
        winner, loser = records = self._duplicate_pair()
        apply_metadata_decisions(records, [self._decision(winner, title="Form (December 1999 edition)")])
        self.assertEqual(winner["title"], "Form (December 1999 edition)")
        self.assertEqual(winner["source_title"], "Form January 2026")
        self.assertEqual(winner["title_basis"], "official_source_review")
        self.assertEqual(winner["robot_text_path"], "TEXT/FOCI/Form January 2026.txt")

    def test_title_override_requires_evidence(self) -> None:
        winner, _ = records = self._duplicate_pair()
        decision = self._decision(winner, title="Renamed", decision="exclude", evidence=[])
        with self.assertRaisesRegex(ValueError, "requires official-source evidence"):
            apply_metadata_decisions(records, [decision])

    def test_provenance_records_url_only_on_identical_bytes(self) -> None:
        winner, _ = self._duplicate_pair()
        winner["human_artifact_sha256"] = "a" * 64
        decision = self._decision(winner, decision="provenance", source_url="https://example.gov/form.pdf",
                                  source_sha256="a" * 64)
        apply_metadata_decisions([winner], [decision])
        self.assertEqual(winner["source_url"], "https://example.gov/form.pdf")
        self.assertEqual(winner["answer_eligibility"], "unresolved_currency")  # lifecycle untouched

    def test_provenance_rejects_different_bytes(self) -> None:
        winner, _ = self._duplicate_pair()
        winner["human_artifact_sha256"] = "a" * 64
        decision = self._decision(winner, decision="provenance", source_url="https://example.gov/form.pdf",
                                  source_sha256="b" * 64)
        with self.assertRaisesRegex(ValueError, "bytes differ"):
            apply_metadata_decisions([winner], [decision])

    def test_ledger_becomes_decisions_for_verified_rows_only(self) -> None:
        from dcsa_custodian.decisions import provenance_decisions
        winner, loser = self._duplicate_pair()
        rows = [{"document_id": "form-mislabelled", "status": "verified", "requested_url": "https://example.gov/a.pdf",
                 "source_sha256": "a" * 64, "checked_utc": "2026-09-18T00:00:00Z", "run_id": "r1"},
                {"document_id": "form-dec1999", "status": "bytes_differ", "requested_url": "https://example.gov/b.pdf",
                 "source_sha256": "b" * 64, "checked_utc": "2026-09-18T00:00:00Z"}]
        made = provenance_decisions(rows, {r["document_id"]: r for r in (winner, loser)}, [])
        self.assertEqual([d["source_document_id"] for d in made], ["form-mislabelled"])
        self.assertEqual(provenance_decisions(rows, {r["document_id"]: r for r in (winner, loser)}, made), [])

    def test_dedup_uses_human_artifact_hash_not_doha_sqlite_side_table(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            # Two DOHA case records for byte-identical source PDFs, differing only in filename
            # and robot-text extraction -- reproduces the real-library bug where one side is
            # present in the DOHA SQLite side-table (with an unrelated content_sha256) and the
            # other falls back to hashing the extracted robot text.
            plain_robot = root / "ROBOT_READABLE_DIRECTORY/TEXT/PERSONNEL_VETTING/DOHA_DECISIONS/case.a1.txt"
            suffixed_robot = root / "ROBOT_READABLE_DIRECTORY/TEXT/PERSONNEL_VETTING/DOHA_DECISIONS/case.a1_denied_F.txt"
            plain_human = root / "HUMAN_READABLE_DIRECTORY/PERSONNEL_VETTING/DOHA_DECISIONS/case.a1.pdf"
            suffixed_human = root / "HUMAN_READABLE_DIRECTORY/PERSONNEL_VETTING/DOHA_DECISIONS/case.a1_denied_F.pdf"
            for path in (plain_robot, suffixed_robot, plain_human, suffixed_human):
                path.parent.mkdir(parents=True, exist_ok=True)
            plain_robot.write_text("extraction pass one of the case text", encoding="utf-8")
            suffixed_robot.write_text("extraction pass two, worded slightly differently", encoding="utf-8")
            plain_human.write_bytes(b"%PDF-identical-case-bytes")
            suffixed_human.write_bytes(b"%PDF-identical-case-bytes")

            records = [
                {
                    "document_id": "case-plain", "collection_id": "doha_decisions", "domain": "personnel_vetting",
                    "human_source_path": "HUMAN_READABLE_DIRECTORY/PERSONNEL_VETTING/DOHA_DECISIONS/case.a1.pdf",
                    "robot_text_path": "ROBOT_READABLE_DIRECTORY/TEXT/PERSONNEL_VETTING/DOHA_DECISIONS/case.a1.txt",
                    "authority_tier": 6, "current_status": "active",
                },
                {
                    "document_id": "case-suffixed", "collection_id": "doha_decisions", "domain": "personnel_vetting",
                    "human_source_path": "HUMAN_READABLE_DIRECTORY/PERSONNEL_VETTING/DOHA_DECISIONS/case.a1_denied_F.pdf",
                    "robot_text_path": "ROBOT_READABLE_DIRECTORY/TEXT/PERSONNEL_VETTING/DOHA_DECISIONS/case.a1_denied_F.txt",
                    "authority_tier": 5, "current_status": "historical_case_research",
                },
            ]
            manifest_path = root / "ROBOT_READABLE_DIRECTORY/MANIFESTS/documents.jsonl"
            write_jsonl(manifest_path, records)

            index = root / "LOCAL_INDEXES/DOHA_CASE_TOPICS_FTS.sqlite"
            index.parent.mkdir(parents=True, exist_ok=True)
            with contextlib.closing(sqlite3.connect(index)) as conn:
                conn.execute(
                    "CREATE TABLE decisions (document_id, answer_eligible, content_sha256, case_id, decision_level, outcome, guideline_codes, current_group)"
                )
                # Only the suffixed record is present in this side-table, with a content_sha256
                # unrelated to the actual (identical) source PDF bytes -- exactly what the real
                # library's DOHA_CASE_TOPICS_FTS.sqlite has for these records.
                conn.execute(
                    "INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?)",
                    ("case-suffixed", 1, "unrelated-hash-from-a-different-pipeline", "case", "a1", "denied", "F", "POST_SEAD_4"),
                )
                conn.commit()

            human_hashes = {
                "case-plain": sha256_file(plain_human),
                "case-suffixed": sha256_file(suffixed_human),
            }
            self.assertEqual(human_hashes["case-plain"], human_hashes["case-suffixed"])  # sanity: identical bytes

            enriched = enrich_manifest(root, manifest_path, human_hashes)
            dupes = [r for r in enriched if r["duplicate_of"] is not None]
            canonicals = [r for r in enriched if r["duplicate_of"] is None]

            # Before the fix: grouped by robot_content_sha256 (SQLite content_sha256 for the
            # suffixed record vs. a robot-text hash for the plain one) -- these never collide,
            # so neither record was ever marked a duplicate of the other. After the fix: both
            # share human_artifact_sha256, so they group correctly.
            self.assertEqual(len(dupes), 1, "expected exactly one record marked duplicate_of the other")
            self.assertEqual(len(canonicals), 1)
            self.assertEqual(dupes[0]["duplicate_of"], canonicals[0]["document_id"])
            self.assertEqual(dupes[0]["answer_eligibility"], "excluded_duplicate")
            self.assertEqual(dupes[0]["answer_eligibility_basis"], "identical_human_artifact_sha256")

    def test_audit_and_candidate_are_preview_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "library"
            project = base / "project"
            root.mkdir()
            project.mkdir()
            self.make_library(root)
            (project / "evals").mkdir()
            write_json(project / "evals/golden_queries.json", {"schema_version": "1.0", "cases": [{"id": "rule", "query": "contractor safeguarding requirement", "require_hit": True, "expected_first_role": "controlling_regulation"}]})
            audit = audit_library(root)
            self.assertTrue(audit["summary"]["integrity_healthy"])
            config = {"state_directory": ".custodian", "default_chunk_characters": 100, "maximum_chunk_characters": 160, "chunk_overlap_characters": 10}
            result = build_candidate(project, root, config, "test-release")
            release_dir = Path(result["release_directory"])
            self.assertTrue(validate_candidate(root, release_dir)["valid"])
            self.assertTrue(validate_candidate(root, release_dir)["publishable"])
            self.assertTrue((release_dir / "reports/REMEDIATION_QUEUE.jsonl").is_file())
            self.assertFalse((root / "ROBOT_READABLE_DIRECTORY/MANIFESTS/DOCUMENTS_ENRICHED.jsonl").exists())

    def test_semantic_index_and_search(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "library"
            project = base / "project"
            root.mkdir()
            project.mkdir()
            self.make_library(root)
            (project / "evals").mkdir()
            write_json(project / "evals/golden_queries.json", {"schema_version": "1.0", "cases": [{"id": "rule", "query": "contractor safeguarding requirement", "require_hit": True, "expected_first_role": "controlling_regulation"}]})
            config = {"state_directory": ".custodian", "default_chunk_characters": 100, "maximum_chunk_characters": 160, "chunk_overlap_characters": 10}
            result = build_candidate(project, root, config, "semantic-test-release")
            release_dir = Path(result["release_directory"])
            validation = validate_candidate(root, release_dir)
            self.assertTrue(validation["valid"], validation["errors"])
            index_entry = next(item for item in validation["indexes"] if item["path"] == "DCSA_CONTROLLING_AUTHORITY_CHUNKS_FTS.sqlite")
            self.assertGreater(index_entry["vectors"], 0)
            self.assertEqual(index_entry["vectors"], index_entry["chunks"])

            db_path = release_dir / "indexes/DCSA_CONTROLLING_AUTHORITY_CHUNKS_FTS.sqlite"
            hits = semantic_search(db_path, "requirement to safeguard classified material for contractors", top_k=3)
            self.assertTrue(hits)
            self.assertEqual(hits[0]["document_id"], "rule")
            self.assertGreater(hits[0]["similarity"], 0.0)

    SEAD3_FIXTURE_TEXT = (
        "A. AUTHORITY\n\nThis directive is issued under such authority.\n\n"
        "F. REPORTABLE ACTIVITIES FOR ALL COVERED INDIVIDUALS\n\n"
        "All covered individuals shall report contact with a foreign national.\n\n"
        "G. REPORTABLE ACTIVITIES FOR INDIVIDUALS WITH ACCESS TO SECRET\n\n"
        "Individuals with Secret access shall additionally report foreign travel.\n\n"
        "H. REPORTABLE ACTIVITIES FOR INDIVIDUALS WITH ACCESS TO TOP SECRET\n\n"
        "Individuals with Top Secret access shall additionally report cohabitation.\n\n"
        "I. RESPONSIBILITIES\n\nAgency heads are responsible for implementation.\n\n"
        "APPENDIX A\n\nRequired data elements are listed here.\n"
    )

    def _sead3_record(self, root: Path) -> dict:
        robot = root / "ROBOT_READABLE_DIRECTORY/TEXT/PERSONNEL_VETTING/SEAD/source.txt"
        human = root / "HUMAN_READABLE_DIRECTORY/PERSONNEL_VETTING/SEAD/source.pdf"
        robot.parent.mkdir(parents=True, exist_ok=True)
        human.parent.mkdir(parents=True, exist_ok=True)
        robot.write_text(self.SEAD3_FIXTURE_TEXT, encoding="utf-8")
        human.write_bytes(b"%PDF-test")
        return {
            "document_id": DIRECTIVE_DOC_IDS["SEAD-3"],
            "collection_id": "sead",
            "domain": "personnel_vetting",
            "authority_tier": 1,
            "current_status": "current",
            "human_source_path": "HUMAN_READABLE_DIRECTORY/PERSONNEL_VETTING/SEAD/source.pdf",
            "robot_text_path": "ROBOT_READABLE_DIRECTORY/TEXT/PERSONNEL_VETTING/SEAD/source.txt",
        }

    def test_directive_split_writes_verified_sections_and_skips_absent_directives(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            records = [self._sead3_record(root)]
            files, problems, skipped = build_directive_splits(root, records)
            self.assertEqual(problems, [])
            # 6 sections + manifest.json + README.md for SEAD-3 only
            sead3_files = [f for f in files if f["relative_path"].startswith(SPLIT_FOLDERS["SEAD-3"])]
            self.assertEqual(len(sead3_files), 8)
            manifest_entry = next(f for f in sead3_files if f["relative_path"].endswith("manifest.json"))
            manifest = json.loads(manifest_entry["content"])
            self.assertEqual(len(manifest["sections"]), 6)
            # SEAD-4 and ISL-2021-02 are simply not in this library -- informational, not an error
            self.assertTrue(any("SEAD-4" in s for s in skipped))
            self.assertTrue(any("ISL-2021-02" in s for s in skipped))
            self.assertFalse(any(f["relative_path"].startswith(SPLIT_FOLDERS["SEAD-4"]) for f in files))

    def test_directive_split_refuses_to_write_on_reassembly_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            record = self._sead3_record(root)
            # Corrupt the source so an anchor appears twice -- the same failure mode the
            # split's reassembly proof exists to catch (see split logic in directive_splits.py).
            path = root / record["robot_text_path"]
            path.write_text(self.SEAD3_FIXTURE_TEXT + "\nA. AUTHORITY\n\nDuplicate anchor.\n",
                             encoding="utf-8")
            files, problems, skipped = build_directive_splits(root, [record])
            sead3_files = [f for f in files if f["relative_path"].startswith(SPLIT_FOLDERS["SEAD-3"])]
            self.assertEqual(sead3_files, [], "nothing should be written when reassembly cannot be proven")
            self.assertTrue(any("SEAD-3" in p and "matched 2 times" in p for p in problems))

    def test_directive_split_is_a_publication_blocker_when_a_present_directive_is_broken(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "library"
            project = base / "project"
            root.mkdir()
            project.mkdir()
            self.make_library(root)
            record = self._sead3_record(root)
            path = root / record["robot_text_path"]
            path.write_text(self.SEAD3_FIXTURE_TEXT + "\nA. AUTHORITY\n\nDuplicate anchor.\n",
                             encoding="utf-8")
            manifest_path = root / "ROBOT_READABLE_DIRECTORY/MANIFESTS/documents.jsonl"
            existing = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            write_jsonl(manifest_path, existing + [record])
            (project / "evals").mkdir()
            write_json(project / "evals/golden_queries.json", {"schema_version": "1.0", "cases": [{"id": "rule", "query": "contractor safeguarding requirement", "require_hit": True, "expected_first_role": "controlling_regulation"}]})
            config = {"state_directory": ".custodian", "default_chunk_characters": 100, "maximum_chunk_characters": 160, "chunk_overlap_characters": 10}
            result = build_candidate(project, root, config, "broken-sead3-release")
            self.assertFalse(result["validation"]["publishable"])
            self.assertTrue(any("directive split" in b for b in result["validation"]["publication_blockers"]))


if __name__ == "__main__":
    unittest.main()
