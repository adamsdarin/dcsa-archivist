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
from dcsa_custodian.common import write_json, write_jsonl
from dcsa_custodian.decisions import apply_metadata_decisions
from dcsa_custodian.release import build_candidate, validate_candidate


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


if __name__ == "__main__":
    unittest.main()
