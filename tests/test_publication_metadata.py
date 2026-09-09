from __future__ import annotations

import json
import contextlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dcsa_custodian.audit import audit_library
from dcsa_custodian.common import read_json, sha256_file, write_json
from dcsa_custodian.release import build_candidate, publish_candidate
from dcsa_custodian.release_contract import approved_release, STATE, POINTER, CATALOG, QUERY, POLICY, CONFIG, ROUTER
import test_custodian


class PublicationMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root, self.project = base / "library", base / "project"
        self.root.mkdir()
        self.project.mkdir()
        test_custodian.CustodianTests().make_library(self.root)
        doha = ["LOCAL_INDEXES/DOHA_CASE_TOPICS_FTS.sqlite", "LOCAL_INDEXES/DOHA_CURRENT_PATHS.sqlite"]
        for relative in doha:
            with contextlib.closing(sqlite3.connect(self.root / relative)) as db:
                db.execute("CREATE TABLE current_paths(document_id TEXT)")
                db.execute("CREATE TABLE decisions(document_id,content_sha256,answer_eligible,case_id,decision_level,outcome,guideline_codes,current_group)")
                db.commit()
        write_json(self.root / CONFIG, {})
        write_json(self.root / POLICY, {"content_access": {"retrieval_forbidden_indexes": ["LOCAL_INDEXES/DCSA_DOHA_DECISIONS_FTS.sqlite"]}})
        write_json(self.root / ROUTER, {"doha_content_index": doha[0], "current_doha_path_index": doha[1]})
        write_json(self.project / "evals/golden_queries.json", {"schema_version": "1.0", "cases": [{"id": "rule", "query": "contractor safeguarding requirement", "require_hit": True, "expected_first_role": "controlling_regulation"}]})
        self.config = {"state_directory": ".custodian", "default_chunk_characters": 100, "maximum_chunk_characters": 160, "chunk_overlap_characters": 10}
        with patch("dcsa_custodian.release.embed_texts", side_effect=lambda texts: [bytes(1536) for _ in texts]):
            result = build_candidate(self.project, self.root, self.config, "metadata-test")
        self.release = Path(result["release_directory"])

    def publish(self):
        return publish_candidate(self.project, self.root, self.config, self.release)

    def test_preview_does_not_mutate_production_and_publish_promotes_state(self):
        before = {p.relative_to(self.root): sha256_file(p) for p in self.root.rglob("*") if p.is_file()}
        candidate_hash = sha256_file(self.release / "production" / STATE)
        preview = publish_candidate(self.project, self.root, self.config, self.release, dry_run=True)
        self.assertEqual(preview["status"], "ready_to_publish")
        self.assertEqual(before, {p.relative_to(self.root): sha256_file(p) for p in self.root.rglob("*") if p.is_file()})
        published = self.publish()
        health = approved_release(self.root, check_integrity=True)
        self.assertTrue(health["state"]["production_response_ready"])
        self.assertEqual(health["state"]["release_status"], "published")
        self.assertEqual(len(health["indexes"]), 6)
        self.assertEqual(len(health["index_checks"]), 8)
        self.assertEqual(candidate_hash, sha256_file(self.release / "production" / STATE))
        self.assertEqual(read_json(self.release / "production" / STATE)["release_status"], "candidate_unapproved")
        self.assertTrue(audit_library(self.root)["summary"]["production_response_ready"])
        self.assertEqual(published["copied"][-1], POINTER)
        for relative, previous_hash in before.items():
            if relative.parts[0] in {"HUMAN_READABLE_DIRECTORY"} or "/TEXT/" in relative.as_posix():
                self.assertEqual(previous_hash, sha256_file(self.root / relative))

    def test_republication_repairs_old_candidate_state_and_saves_pointer(self):
        first = self.publish()
        state = read_json(self.root / STATE)
        state.update(release_status="candidate_unapproved", production_response_ready=False, approved_indexes=[])
        write_json(self.root / STATE, state)
        with self.assertRaisesRegex(ValueError, "not published"):
            approved_release(self.root)
        before = audit_library(self.root)
        self.assertTrue(before["summary"]["integrity_healthy"])
        self.assertFalse(before["summary"]["production_response_ready"])
        self.assertTrue(before["release_metadata_errors"])
        second = self.publish()
        self.assertEqual(second["pointer"]["approval"], first["pointer"]["approval"])
        backup = Path(second["pointer"]["rollback_snapshot"])
        self.assertEqual(read_json(backup / POINTER), first["pointer"])
        self.assertEqual(read_json(backup / STATE)["release_status"], "candidate_unapproved")
        self.assertFalse(any(relative.endswith(".sqlite") for relative in second["copied"]))

    def test_preflight_rejects_drift_missing_indexes_and_ineligible_content(self):
        self.publish()
        path = self.root / QUERY
        original = path.read_bytes()
        data = read_json(path)
        data["release_id"] = "some-other-release"
        write_json(path, data)
        with self.assertRaisesRegex(ValueError, "disagree on release ID"):
            approved_release(self.root)
        path.write_bytes(original)
        index = self.root / read_json(self.root / CATALOG)["indexes"][0]["production_path"]
        moved = index.with_suffix(".missing")
        index.rename(moved)
        with self.assertRaisesRegex(ValueError, "index missing"):
            approved_release(self.root)
        moved.rename(index)
        with contextlib.closing(sqlite3.connect(index)) as db:
            db.execute("UPDATE corpus SET answer_eligibility='unresolved_currency'")
            db.commit()
        with self.assertRaisesRegex(ValueError, "Ineligible content"):
            approved_release(self.root)

    def test_preflight_rejects_stale_agent_instructions_and_path_escape(self):
        self.publish()
        (self.root / "AGENTS.md").write_text("General retrieval uses `LOCAL_INDEXES/DCSA_GENERAL_FTS.sqlite`", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "retired general index"):
            approved_release(self.root)
        self.publish()
        for relative in (STATE, CATALOG, QUERY):
            data = read_json(self.root / relative)
            key = "approved_indexes" if relative == STATE else "indexes"
            data[key][0]["production_path"] = "LOCAL_INDEXES/CUSTODIAN/metadata-test/../../escape.sqlite"
            if relative == CATALOG:
                data["default_sequence"][0] = data[key][0]["production_path"]
            write_json(self.root / relative, data)
        with self.assertRaisesRegex(ValueError, "Path outside"):
            approved_release(self.root)


if __name__ == "__main__":
    unittest.main()
