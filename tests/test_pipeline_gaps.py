"""Gaps a rehearsal of the monthly intake showed: receipts with unheld documents, derived-artifact
drift, the collection catalog, the embedding cache location and the audit run before staging."""
from __future__ import annotations

import contextlib
import io
import json
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from dcsa_custodian import cli, release
from dcsa_custodian.audit import audit_library
from dcsa_custodian.catalog import catalog_differences, collection_catalog
from dcsa_custodian.common import read_json, sha256_file, write_json
from dcsa_custodian.events import acknowledge, acknowledgment_states, acquisition_request_path, event_directory, pending_events
from dcsa_custodian.release import build_candidate, embedding_cache_path, publish_candidate, seed_embedding_cache
import test_publication_metadata as fixtures
import test_release_handoffs as handoffs

MANIFEST = "ROBOT_READABLE_DIRECTORY/MANIFESTS/documents.jsonl"
RELATIONSHIPS = "ROBOT_READABLE_DIRECTORY/MANIFESTS/relationships.jsonl"
CATALOG = "ROBOT_READABLE_DIRECTORY/CATALOG/COLLECTIONS.json"


class Base(unittest.TestCase):
    setUp = fixtures.PublicationMetadataTests.setUp
    publish = fixtures.PublicationMetadataTests.publish
    plan = handoffs.HandoffTests.plan
    build = handoffs.HandoffTests.build

    def run_cli(self, *arguments: str) -> tuple[int, dict]:
        config = self.project / "cli.config.json"
        write_json(config, {**self.config, "library_root": str(self.root), "state_directory": str(self.project / ".custodian")})
        output = io.StringIO()
        with patch.object(sys, "argv", ["custodian.py", "--config", str(config), *arguments]), contextlib.redirect_stdout(output):
            code = cli.main()
        return code, json.loads(output.getvalue())

    def publish_intake(self) -> dict:
        self.publish()
        plan, record = self.plan()
        publish_candidate(self.project, self.root, self.config, Path(self.build(plan)["release_directory"]))
        return record


class GapReceiptTests(Base):
    UNHELD = {"title": "Industrial Security Letter the issue cites", "cited_at": "SOURCE PAGE 4, second paragraph",
              "needed_for": "closing the citation behind one finding",
              "handling": "wrote only what the issue itself says and marked coverage incomplete"}

    def receipt(self, **changes) -> Path:
        self.publish()
        event = read_json(event_directory(self.project, self.config, self.root) / self.release.name / "event.json")
        artifact = self.project / "review.md"
        artifact.write_text("Synthetic full-source review with one citation left open.", encoding="utf-8")
        self.body = {"event_id": self.release.name, "consumer": "fso-guidance-watch", "changes_sha256": event["changes_sha256"],
                     "status": "completed_with_gaps", "reviewed_by": "test-agent", "summary": "Synthetic review.",
                     "full_source_review": True, "citation_closure": False, "coverage_complete": False,
                     "unheld_documents": [dict(self.UNHELD)],
                     "artifacts": [{"path": "review.md", "sha256": sha256_file(artifact)}]}
        self.body.update(changes)
        self.path = self.project / "receipt.json"
        write_json(self.path, self.body)
        return self.path

    def ack(self, **changes) -> dict:
        if not hasattr(self, "body"):
            self.receipt()
        self.body.update(changes)
        write_json(self.path, self.body)
        return acknowledge(self.project, self.config, self.root, "fso-guidance-watch", self.release.name, self.path)

    def test_a_receipt_with_gaps_is_accepted_recorded_and_turned_into_an_acquisition_request(self) -> None:
        result = self.ack()
        self.assertEqual((result["status"], result["acknowledgment"], result["unheld_documents"]),
                         ("completed_with_gaps", "acknowledged_with_gaps", 1))
        stored = read_json(Path(result["receipt"]))
        self.assertEqual(stored["acknowledgment"], "acknowledged_with_gaps")
        self.assertEqual(stored["unheld_documents"], [self.UNHELD])
        request_path = acquisition_request_path(self.project, self.config, self.release.name, "fso-guidance-watch")
        self.assertEqual(request_path, self.project / ".custodian/acquisition-requests" / f"{self.release.name}.fso-guidance-watch.json")
        request = read_json(request_path)
        self.assertEqual((request["type"], request["status"], request["requests"]), ("library.acquisition_request", "open", [self.UNHELD]))
        self.assertEqual(stored["acquisition_request"], str(request_path))
        # acknowledged, so no longer pending; and not silent either
        self.assertFalse(pending_events(self.project, self.config, self.root, "fso-guidance-watch"))
        self.assertTrue(pending_events(self.project, self.config, self.root, "dcsa-compare"))
        state = acknowledgment_states(self.project, self.config, self.root)[0]["consumers"]
        self.assertEqual(state["fso-guidance-watch"]["state"], "acknowledged_with_gaps")
        self.assertEqual(state["fso-guidance-watch"]["unheld_documents"], [self.UNHELD])
        self.assertEqual(state["dcsa-compare"]["state"], "pending")
        code, events = self.run_cli("events", "--library-root", str(self.root), "--consumer", "fso-guidance-watch")
        self.assertEqual((code, events["status"]), (0, "no_pending_events"))
        self.assertEqual([(row["event_id"], row["state"], row["acquisition_request"]) for row in events["acknowledged_with_gaps"]],
                         [(self.release.name, "acknowledged_with_gaps", str(request_path))])
        code, status = self.run_cli("status")
        self.assertEqual(status["consumer_acknowledgments"][0]["consumers"]["fso-guidance-watch"]["state"], "acknowledged_with_gaps")

    def test_one_gate_may_still_be_true(self) -> None:
        self.assertEqual(self.ack(citation_closure=True, coverage_complete=False)["acknowledgment"], "acknowledged_with_gaps")

    def test_each_way_a_receipt_with_gaps_is_refused(self) -> None:
        cases = [
            ({"full_source_review": False}, "incomplete consumer gate: full_source_review"),
            ({"unheld_documents": []}, "non-empty unheld_documents"),
            ({"unheld_documents": None}, "non-empty unheld_documents"),
            ({"unheld_documents": "one letter"}, "non-empty unheld_documents"),
            ({"unheld_documents": ["one letter"]}, "each unheld document needs"),
            ({"citation_closure": True, "coverage_complete": True}, "every gate complete while listing unheld_documents"),
            ({"citation_closure": None}, "stated true or false"),
            ({"coverage_complete": "no"}, "stated true or false"),
            # any other status keeps the existing rule, and may not list unheld documents at all
            ({"status": "completed"}, "unheld_documents requires status completed_with_gaps"),
            ({"status": "completed", "citation_closure": True, "coverage_complete": True},
             "unheld_documents requires status completed_with_gaps"),
            ({"status": "no_relevant_change", "citation_closure": True, "coverage_complete": True},
             "unheld_documents requires status completed_with_gaps"),
            ({"status": "completed", "unheld_documents": []}, "incomplete consumer gate: citation_closure"),
            ({"status": "partial"}, "reviewed completion"),
        ]
        for field in ("title", "cited_at", "needed_for", "handling"):
            cases.append(({"unheld_documents": [{**self.UNHELD, field: "  "}]}, "each unheld document needs"))
            cases.append(({"unheld_documents": [{key: value for key, value in self.UNHELD.items() if key != field}]},
                          "each unheld document needs"))
        for changes, message in cases:
            with self.subTest(changes=changes):
                self.receipt() if not hasattr(self, "body") else None
                original = dict(self.body)
                with self.assertRaisesRegex(ValueError, message):
                    self.ack(**changes)
                self.body = original
        directory = event_directory(self.project, self.config, self.root) / self.release.name
        self.assertFalse((directory / "fso-guidance-watch.receipt.json").exists())
        self.assertFalse((self.project / ".custodian/acquisition-requests").exists())
        self.assertTrue(pending_events(self.project, self.config, self.root, "fso-guidance-watch"))

    def test_a_complete_receipt_is_still_recorded_as_acknowledged(self) -> None:
        result = self.ack(status="completed", citation_closure=True, coverage_complete=True, unheld_documents=[])
        self.assertEqual(result["acknowledgment"], "acknowledged")
        self.assertNotIn("acquisition_request", result)
        self.assertFalse((self.project / ".custodian/acquisition-requests").exists())
        code, events = self.run_cli("events", "--library-root", str(self.root), "--consumer", "fso-guidance-watch")
        self.assertEqual(events["acknowledged_with_gaps"], [])

    def test_a_stored_gap_receipt_that_is_edited_returns_to_pending(self) -> None:
        stored = Path(self.ack()["receipt"])
        receipt = read_json(stored)
        receipt["unheld_documents"] = []
        write_json(stored, receipt)
        self.assertTrue(pending_events(self.project, self.config, self.root, "fso-guidance-watch"))


class DerivedAgreementTests(Base):
    def rows(self, relative: str) -> list[dict]:
        return [json.loads(line) for line in (self.root / relative).read_text(encoding="utf-8").splitlines() if line.strip()]

    def write_rows(self, relative: str, rows: list[dict]) -> None:
        (self.root / relative).write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8", newline="\n")

    def test_a_published_library_agrees_and_an_unpublished_one_is_not_judged(self) -> None:
        self.assertIsNone(audit_library(self.root)["summary"]["derived_artifacts_agree"])
        self.publish_intake()
        report = audit_library(self.root)
        self.assertIs(report["summary"]["derived_artifacts_agree"], True)
        self.assertEqual({item["artifact"].rsplit("/", 1)[-1] for item in report["derived_artifacts"]["artifacts"]} >=
                         {"DOCUMENTS_ENRICHED.jsonl", "GENERAL_CITATION_SAFE_CHUNKS.jsonl", "GRAPH.json"}, True)
        self.assertEqual(self.run_cli("doctor")[0], 0)

    def test_a_document_removed_from_the_manifest_by_hand_is_reported_as_stale_everywhere(self) -> None:
        self.publish_intake()
        self.write_rows(MANIFEST, [row for row in self.rows(MANIFEST) if row["document_id"] != "new-voi"])
        self.write_rows(RELATIONSHIPS, [row for row in self.rows(RELATIONSHIPS) if row["document_id"] != "new-voi"])
        report = audit_library(self.root)
        self.assertTrue(report["summary"]["integrity_healthy"])  # every per-record check still passes
        self.assertIs(report["summary"]["derived_artifacts_agree"], False)
        warning = next(item for item in report["warnings"] if item["code"] == "derived_artifact_drift")
        stale = {item["artifact"].rsplit("/", 1)[-1]: item.get("stale_sample") for item in warning["artifacts"]}
        for name in ("DOCUMENTS_ENRICHED.jsonl", "GENERAL_CITATION_SAFE_CHUNKS.jsonl", "GRAPH.json"):
            self.assertEqual(stale[name], ["new-voi"])
        self.assertTrue(any(name.endswith(".sqlite") for name in stale))
        code, doctor = self.run_cli("doctor")
        self.assertEqual((code, doctor["derived_artifacts_agree"]), (2, False))
        self.assertTrue(doctor["derived_artifact_drift"])

    def test_a_document_added_to_the_manifest_by_hand_is_reported_as_missing(self) -> None:
        self.publish()
        rows = self.rows(MANIFEST)
        extra = {**rows[0], "document_id": "hand-added"}
        self.write_rows(MANIFEST, rows + [extra])
        self.write_rows(RELATIONSHIPS, self.rows(RELATIONSHIPS) + [
            {"relation": "machine_readable_representation_of", **{key: extra[key] for key in ("document_id", "human_source_path", "robot_text_path")}}])
        report = audit_library(self.root)
        self.assertIs(report["summary"]["derived_artifacts_agree"], False)
        enriched = next(item for item in report["derived_artifacts"]["artifacts"] if item["artifact"].endswith("DOCUMENTS_ENRICHED.jsonl"))
        self.assertEqual(enriched["missing_sample"], ["hand-added"])
        # a build may name what it has just staged; nothing else is excused
        self.assertIs(audit_library(self.root, pending_intake={"hand-added"})["summary"]["derived_artifacts_agree"], True)
        self.assertIs(audit_library(self.root, pending_intake={"something-else"})["summary"]["derived_artifacts_agree"], False)

    def test_a_stale_derived_file_is_reported(self) -> None:
        self.publish_intake()
        chunks = "ROBOT_READABLE_DIRECTORY/CHUNKS/GENERAL_CITATION_SAFE_CHUNKS.jsonl"
        self.write_rows(chunks, [row for row in self.rows(chunks) if row["document_id"] != "new-voi"])
        report = audit_library(self.root)
        item = next(item for item in report["derived_artifacts"]["artifacts"] if item["artifact"] == chunks)
        self.assertEqual(item["missing_sample"], ["new-voi"])
        self.assertIs(report["summary"]["derived_artifacts_agree"], False)

    def test_a_repeated_relationship_row_is_reported(self) -> None:
        self.publish()
        rows = self.rows(RELATIONSHIPS)
        self.write_rows(RELATIONSHIPS, rows + rows[:1])
        report = audit_library(self.root)
        self.assertTrue(report["summary"]["integrity_healthy"])
        self.assertEqual(next(item for item in report["warnings"] if item["code"] == "duplicate_relationship_rows")["count"], 1)

    def test_an_intake_build_excuses_only_what_it_staged(self) -> None:
        self.publish()
        plan, _ = self.plan()
        audit = read_json(Path(self.build(plan)["release_directory"]) / "reports/PRODUCTION_AUDIT.json")
        self.assertIs(audit["summary"]["derived_artifacts_agree"], True)
        self.assertEqual(audit["derived_artifacts"]["pending_intake"], 1)


class CollectionCatalogTests(Base):
    def test_catalog_is_derived_and_keeps_reviewed_keys(self) -> None:
        records = [{"collection_id": "voi", "domain": "industrial_security", "authority_tier": 7},
                   {"collection_id": "voi", "domain": "INDUSTRIAL_SECURITY", "authority_tier": 7},
                   {"collection_id": "cfr", "domain": "authorities", "authority_tier": 1}]
        existing = [{"collection_id": "voi", "document_count": 1, "domains": ["industrial_security"], "authority_tiers": ["7"], "note": "kept"},
                    {"collection_id": "rmf", "document_count": 2, "domains": ["x"], "authority_tiers": ["3"]}]
        self.assertEqual([d["collection_id"] for d in catalog_differences(existing, records)], ["cfr", "rmf", "voi"])
        catalog = collection_catalog(records, existing)
        self.assertEqual(catalog, [
            {"collection_id": "voi", "document_count": 2, "domains": ["industrial_security"], "authority_tiers": ["7"], "note": "kept"},
            {"collection_id": "rmf", "document_count": 0, "domains": ["x"], "authority_tiers": ["3"]},
            {"collection_id": "cfr", "document_count": 1, "domains": ["authorities"], "authority_tiers": ["1"]}])
        self.assertEqual(catalog_differences(catalog, records), [])

    def test_a_tool_only_intake_publishes_the_right_counts(self) -> None:
        self.publish()
        entry = read_json(self.root / "START_HERE_FOR_ROBOTS.json")
        write_json(self.root / "START_HERE_FOR_ROBOTS.json", {**entry, "catalog": CATALOG})
        nested = read_json(self.root / "ROBOT_READABLE_DIRECTORY/START_HERE.json")
        write_json(self.root / "ROBOT_READABLE_DIRECTORY/START_HERE.json", {**nested, "catalog": CATALOG})
        write_json(self.root / CATALOG, [{"collection_id": "cfr", "document_count": 7, "domains": ["authorities"], "authority_tiers": ["1"]}])
        before = audit_library(self.root)
        self.assertIs(before["summary"]["collection_catalog_agrees"], False)
        self.assertTrue(before["summary"]["integrity_healthy"])
        self.assertTrue(any(item["code"] == "collection_catalog_drift" for item in before["warnings"]))
        plan, _ = self.plan()
        candidate = Path(self.build(plan)["release_directory"])
        self.assertEqual(read_json(self.root / CATALOG)[0]["document_count"], 7)  # staged, not written
        preview = publish_candidate(self.project, self.root, self.config, candidate, dry_run=True)
        self.assertIn(CATALOG, preview["changed_files"])
        publish_candidate(self.project, self.root, self.config, candidate)
        self.assertEqual({item["collection_id"]: item["document_count"] for item in read_json(self.root / CATALOG)}, {"cfr": 1, "voi": 1})
        self.assertIs(audit_library(self.root)["summary"]["collection_catalog_agrees"], True)

    def test_validation_refuses_a_catalog_that_miscounts_the_candidate(self) -> None:
        entry = read_json(self.root / "START_HERE_FOR_ROBOTS.json")
        write_json(self.root / "START_HERE_FOR_ROBOTS.json", {**entry, "catalog": CATALOG})
        with patch("dcsa_custodian.release.embed_texts", side_effect=lambda texts: [bytes(1536) for _ in texts]):
            result = build_candidate(self.project, self.root, self.config, "catalog-test")
        self.assertTrue(result["validation"]["valid"])
        staged = Path(result["release_directory"]) / "production" / CATALOG
        write_json(staged, [{"collection_id": "cfr", "document_count": 9, "domains": ["authorities"], "authority_tiers": ["1"]}])
        errors = release.validate_candidate(self.root, Path(result["release_directory"]))["errors"]
        self.assertTrue(any("collection catalog disagrees" in error for error in errors))


class BuildCostTests(Base):
    def test_the_library_is_hashed_once_per_intake_build_and_the_gate_before_staging_stays(self) -> None:
        self.publish()
        plan, _ = self.plan()
        calls = []

        def spy(root, deep=False, **options):
            calls.append((Path(root).resolve() == self.root.resolve(), deep))
            return audit_library(root, deep=deep, **options)
        with patch("dcsa_custodian.release.audit_library", side_effect=spy):
            result = self.build(plan)
        # first the library itself (gate, no byte hashing), then the staged copy (hashes for enrichment)
        self.assertEqual(calls, [(True, False), (False, True)])
        self.assertTrue(read_json(Path(result["release_directory"]) / "reports/PRODUCTION_AUDIT.json")["human_hashes"])
        # the same errors stop the build before anything is staged
        (self.root / "ROBOT_READABLE_DIRECTORY/TEXT/AUTHORITIES/CFR/rule.txt").unlink()
        self.assertEqual([error["code"] for error in audit_library(self.root, deep=False)["errors"]],
                         [error["code"] for error in audit_library(self.root, deep=True)["errors"]])
        with self.assertRaisesRegex(RuntimeError, "production audit failed before staging"):
            self.build(plan, "blocked")
        self.assertFalse((self.project / ".custodian/releases/blocked").exists())
        self.assertFalse(list((self.project / ".custodian").glob("intake-*")))

    def test_the_embedding_cache_location_is_configurable_and_can_be_seeded_read_only(self) -> None:
        self.assertEqual(embedding_cache_path(self.project, {"state_directory": ".custodian"}), self.project / ".custodian/embedding_cache.sqlite")
        elsewhere = self.project / "relocated-state"
        self.assertEqual(embedding_cache_path(self.project, {"state_directory": str(elsewhere)}), elsewhere / "embedding_cache.sqlite")
        shared = self.project / "shared/cache.sqlite"
        self.assertEqual(embedding_cache_path(self.project, {"state_directory": str(elsewhere), "embedding_cache": str(shared)}), shared)
        seed = self.project / "seed.sqlite"
        with contextlib.closing(sqlite3.connect(seed)) as db:
            db.execute("CREATE TABLE vectors(model TEXT, content_sha256 TEXT, vector BLOB, PRIMARY KEY(model, content_sha256))")
            db.execute("INSERT INTO vectors VALUES('m','k',x'00')")
            db.commit()
        digest = sha256_file(seed)
        config = {"state_directory": str(elsewhere), "embedding_cache_seed": str(seed)}
        cache = embedding_cache_path(self.project, config)
        self.assertEqual(seed_embedding_cache(self.project, config, cache), {"seed": str(seed), "copied": True})
        with contextlib.closing(sqlite3.connect(cache)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM vectors").fetchone()[0], 1)
            db.execute("INSERT INTO vectors VALUES('m','new',x'01')")
            db.commit()
        self.assertEqual(sha256_file(seed), digest)  # the seed is never written
        self.assertIsNone(seed_embedding_cache(self.project, config, cache))  # an existing cache is kept
        missing = {"state_directory": str(self.project / "third"), "embedding_cache_seed": str(self.project / "absent.sqlite")}
        self.assertFalse(seed_embedding_cache(self.project, missing, embedding_cache_path(self.project, missing))["copied"])


if __name__ == "__main__":
    unittest.main()
