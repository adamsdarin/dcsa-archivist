import contextlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from dcsa_custodian.evals import evaluate_candidate


class EvaluationTests(unittest.TestCase):
    def evaluate(self, case, content="Required synthetic passage.", semantic=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = root / "production/ROBOT_READABLE_DIRECTORY/RETRIEVAL/INDEX_CATALOG.json"
            catalog.parent.mkdir(parents=True)
            catalog.write_text(json.dumps({"indexes": [{"path": "index.sqlite", "default_allowed": True, "allowed_intents": ["general_current"]}, {"path": "forbidden.sqlite", "default_allowed": False}]}))
            with contextlib.closing(sqlite3.connect(root / "index.sqlite")) as db:
                db.execute("CREATE VIRTUAL TABLE corpus USING fts5(chunk_id,document_id,authority_role,authority_priority,collection_id,locator,content)")
                db.execute("INSERT INTO corpus VALUES('c1','rule','controlling_regulation',10,'cfr','page:1',?)", (content,))
                db.commit()
            cases = root / "cases.json"
            cases.write_text(json.dumps({"cases": [dict(id="test", query="synthetic", **case)]}))
            if semantic:
                with patch("dcsa_custodian.evals.semantic_search", return_value=[dict(chunk_id="c1",document_id="rule",authority_role="controlling_regulation",locator="page:1",content=content)]) as search:
                    result = evaluate_candidate(root, cases)
                    self.assertEqual(search.call_count, 1)
                    self.assertEqual(search.call_args.args[0].name, "index.sqlite")
                    return result
            return evaluate_candidate(root, cases)

    def test_wrong_document_or_wrong_passage_fails_even_with_correct_role(self):
        self.assertFalse(self.evaluate(dict(require_hit=True, expected_document_ids=["different"]))["passed"])
        self.assertFalse(self.evaluate(dict(require_hit=True, expected_passages=["not in source"]))["passed"])
        self.assertTrue(self.evaluate(dict(require_hit=True, expected_document_ids=["rule"], expected_passages=["Required synthetic passage"], require_locator=True))["passed"])

    def test_required_hit_and_explicit_abstention(self):
        self.assertFalse(self.evaluate(dict(require_hit=True), "Unrelated text")["passed"])
        self.assertTrue(self.evaluate(dict(require_abstain=True), "Unrelated text")["passed"])
        self.assertFalse(self.evaluate(dict(require_abstain=True))["passed"])

    def test_semantic_uses_same_passage_assertions_and_eligible_indexes(self):
        self.assertTrue(self.evaluate(dict(retrieval_mode="semantic", require_hit=True, expected_document_ids=["rule"], expected_passages=["synthetic"]), semantic=True)["passed"])
        self.assertFalse(self.evaluate(dict(retrieval_mode="semantic", require_hit=True, expected_passages=["absent"]), semantic=True)["passed"])
