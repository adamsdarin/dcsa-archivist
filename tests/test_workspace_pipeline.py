"""Offline cross-repository acceptance: real pipeline, synthetic source bytes.

The explicit intake step represents the maintainer's source/parity acceptance;
discovery is intentionally unable to approve or publish it on its own.
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import unittest
from unittest.mock import patch

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE / "dcsa-librarian/src"))
from library_custodian.discovery import discover
from dcsa_custodian.common import write_json, write_jsonl, sha256_file
from dcsa_custodian.release import build_candidate, publish_candidate
from dcsa_custodian.release_contract import readiness
import test_publication_metadata as metadata_fixtures

spec = importlib.util.spec_from_file_location("workspace_bot", WORKSPACE / "fso-question-bot/fso-question-bot/scripts/fso_bot.py")
bot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)


class WorkspacePipelineTests(unittest.TestCase):
    setUp = metadata_fixtures.PublicationMetadataTests.setUp
    publish = metadata_fixtures.PublicationMetadataTests.publish
    def test_discovery_quarantine_intake_renamed_source_publish_and_citation(self):
        registry = self.project / "registry.json"
        write_json(registry, {"sources": [{"id": "synthetic", "url": "https://www.dcsa.mil/resources/", "allowed_domains": ["dcsa.mil"]}]})
        body = b"%PDF-synthetic-update"
        class Fetcher:
            def __init__(self, **kwargs): pass
            def get(self, url):
                if url.endswith(".pdf"):
                    return body, {"content_type": "application/pdf"}
                return b'<a href="/docs/renamed-rule.pdf">Synthetic rule</a>', {"content_type": "text/html"}
        before = sha256_file(self.root / "ROBOT_READABLE_DIRECTORY/MANIFESTS/documents.jsonl")
        with patch("library_custodian.discovery.Fetcher", Fetcher):
            report = discover(self.root, registry, self.project / "state", self.project / "quarantine", download=True, verify_known=False)
        self.assertEqual(report["counts"]["downloaded_to_quarantine"], 1)
        self.assertEqual(before, sha256_file(self.root / "ROBOT_READABLE_DIRECTORY/MANIFESTS/documents.jsonl"))
        acquired = next((self.project / "quarantine").rglob("*.pdf"))
        self.assertEqual(acquired.read_bytes(), body)
        manifest = self.root / "ROBOT_READABLE_DIRECTORY/MANIFESTS/documents.jsonl"
        original = json.loads(manifest.read_text().splitlines()[0])
        old = dict(original, document_id="old-rule", current_status="superseded")
        updated = dict(original, human_source_path="HUMAN_READABLE_DIRECTORY/AUTHORITIES/CFR/renamed-rule.pdf", robot_text_path="ROBOT_READABLE_DIRECTORY/TEXT/AUTHORITIES/CFR/renamed-rule.txt", canonical_source_uri="https://www.dcsa.mil/docs/renamed-rule.pdf")
        shutil.copy2(acquired, self.root / updated["human_source_path"])
        (self.root / updated["robot_text_path"]).write_text("TIER: 1\nSTATUS: current\nDOC TYPE: regulation\n\nContractor safeguarding requirement. Updated synthetic passage.")
        write_jsonl(manifest, [old, updated])
        write_jsonl(manifest.with_name("relationships.jsonl"), [{"relation": "machine_readable_representation_of", **{k: row[k] for k in ("document_id", "human_source_path", "robot_text_path")}} for row in (old, updated)])
        with patch("dcsa_custodian.release.embed_texts", side_effect=lambda texts: [bytes(1536) for _ in texts]):
            result = build_candidate(self.project, self.root, self.config, "updated-source")
        publish_candidate(self.project, self.root, self.config, Path(result["release_directory"]))
        self.assertTrue(readiness(self.root)["ready"])
        hits = bot.query_release(self.root, "contractor safeguarding requirement", 5)
        self.assertTrue(hits)
        self.assertTrue(all(h["document_id"] == "rule" for h in hits))
        self.assertEqual(hits[0]["human_source_path"], updated["human_source_path"])
        self.assertTrue(hits[0]["locator"])
        self.assertIn("Updated synthetic passage", hits[0]["content"])

    def test_interrupted_publication_fails_closed_and_retry_recovers(self):
        real_replace = os.replace
        def interrupt(source, target):
            if str(target).endswith("CURRENT_CUSTODIAN_RELEASE.json"):
                raise OSError("synthetic interruption before pointer swap")
            return real_replace(source, target)
        with patch("dcsa_custodian.release.os.replace", side_effect=interrupt):
            with self.assertRaisesRegex(OSError, "synthetic interruption"):
                self.publish()
        self.assertFalse(readiness(self.root)["ready"])
        with self.assertRaises((OSError, ValueError)):
            bot.query_release(self.root, "safeguarding", 5)
        self.publish()
        self.assertTrue(readiness(self.root)["ready"])
        self.assertTrue(bot.query_release(self.root, "safeguarding", 5))

    def test_old_passing_report_cannot_bypass_stronger_current_evaluation(self):
        write_json(self.project / "evals/golden_queries.json", {"cases": [{"id": "new-required", "query": "absentnewrequirement", "require_hit": True}]})
        with self.assertRaisesRegex(RuntimeError, "current retrieval evaluation"):
            self.publish()
        self.assertFalse((self.release / "APPROVAL.json").exists())
