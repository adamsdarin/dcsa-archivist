from __future__ import annotations

import contextlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from .common import read_json, utc_now


STOP = {"a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "of", "on", "or", "the", "to", "under", "with"}


def _expression(query: str) -> str:
    tokens = [token.lower() for token in re.findall(r"[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*", query) if len(token) > 1 and token.lower() not in STOP]
    return " AND ".join(f'"{token}"' for token in tokens[:12])


def evaluate_candidate(release_dir: Path, eval_file: Path) -> dict[str, Any]:
    catalog = read_json(release_dir / "production/ROBOT_READABLE_DIRECTORY/RETRIEVAL/INDEX_CATALOG.json")
    cases = read_json(eval_file)["cases"]
    results = []
    for case in cases:
        intent = case.get("intent", "general_current")
        default_indexes = [
            item for item in catalog["indexes"]
            if item["default_allowed"] and intent in item.get("allowed_intents", ["general_current"])
        ]
        default_indexes.sort(key=lambda item: (item.get("retrieval_stage", 99), item["path"]))
        hits: list[dict[str, Any]] = []
        selected_index = None
        expression = _expression(case["query"])
        for item in default_indexes:
            db_path = release_dir / item["path"]
            with contextlib.closing(sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)) as conn:
                conn.row_factory = sqlite3.Row
                rows = list(conn.execute("""
                    SELECT chunk_id,document_id,authority_role,authority_priority,collection_id,locator,
                           bm25(corpus) AS relevance
                    FROM corpus WHERE corpus MATCH ?
                    ORDER BY authority_priority ASC,relevance ASC LIMIT 5
                """, (expression,)))
            if rows:
                selected_index = item["path"]
                hits = [dict(row) for row in rows]
                break
        failures = []
        if case.get("require_hit") and not hits:
            failures.append("required hit missing")
        if not hits and not case.get("allow_abstain") and not case.get("require_hit"):
            failures.append("unexpected abstention")
        expected_roles = case.get("expected_first_roles")
        if not expected_roles and case.get("expected_first_role"):
            expected_roles = [case["expected_first_role"]]
        if hits and expected_roles and hits[0]["authority_role"] not in expected_roles:
            failures.append(f"first role {hits[0]['authority_role']} not in {expected_roles}")
        if hits and hits[0]["authority_role"] in case.get("forbidden_first_roles", []):
            failures.append(f"forbidden first role: {hits[0]['authority_role']}")
        results.append({"id": case["id"], "query": case["query"], "intent": intent, "selected_index": selected_index, "hits": hits, "abstained": not hits, "passed": not failures, "failures": failures})
    passed = sum(item["passed"] for item in results)
    return {"schema_version": "1.0", "evaluated_utc": utc_now(), "passed": passed == len(results), "passed_cases": passed, "total_cases": len(results), "results": results}
