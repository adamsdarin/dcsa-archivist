from __future__ import annotations

import collections
import contextlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from .authority import parse_authority_header
from .common import HUMAN_PREFIX, ROBOT_PREFIX, iter_jsonl, norm, read_json, safe_relative, sha256_file, utc_now
from . import doha_release
from .release_contract import approved_release, bounded_path


REQUIRED_FIELDS = {
    "document_id", "collection_id", "authority_tier", "current_status",
    "human_source_path", "robot_text_path",
}


def _doha_hashes(root: Path) -> tuple[dict[str, str], dict[str, bool]]:
    hashes: dict[str, str] = {}
    eligible: dict[str, bool] = {}
    path = root / "LOCAL_INDEXES/DOHA_CASE_TOPICS_FTS.sqlite"
    if not path.is_file():
        return hashes, eligible
    with contextlib.closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as conn:
        for document_id, digest, answer_eligible in conn.execute("SELECT document_id,content_sha256,answer_eligible FROM decisions"):
            hashes[document_id] = digest
            eligible[document_id] = bool(answer_eligible)
    return hashes, eligible


def audit_library(root: Path, deep: bool = False) -> dict[str, Any]:
    entry_path = root / "START_HERE_FOR_ROBOTS.json"
    if not entry_path.is_file():
        raise FileNotFoundError(entry_path)
    entry = read_json(entry_path)
    manifest_path = root / norm(entry["documents"])
    relationships_path = root / norm(entry["relationships"])
    doha_hashes, _ = _doha_hashes(root)

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    id_lines: dict[str, list[int]] = collections.defaultdict(list)
    content_groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    statuses: collections.Counter[str] = collections.Counter()
    collections_count: collections.Counter[str] = collections.Counter()
    tier_conflicts: list[dict[str, Any]] = []
    human_hashes: dict[str, str] = {}

    for line_number, record in iter_jsonl(manifest_path):
        records.append(record)
        missing = sorted(REQUIRED_FIELDS - record.keys())
        if missing:
            errors.append({"code": "manifest_missing_fields", "line": line_number, "fields": missing})
            continue
        document_id = str(record["document_id"])
        id_lines[document_id].append(line_number)
        statuses[str(record.get("current_status"))] += 1
        collections_count[str(record.get("collection_id"))] += 1
        try:
            robot_rel = safe_relative(record["robot_text_path"], ROBOT_PREFIX)
            human_rel = safe_relative(record["human_source_path"], HUMAN_PREFIX)
        except ValueError as exc:
            errors.append({"code": "path_boundary", "line": line_number, "document_id": document_id, "message": str(exc)})
            continue
        robot_path = root / robot_rel
        human_path = root / human_rel
        if not robot_path.is_file():
            errors.append({"code": "missing_robot", "line": line_number, "document_id": document_id, "path": robot_rel})
            continue
        if not human_path.is_file():
            errors.append({"code": "missing_human_parity_artifact", "line": line_number, "document_id": document_id, "path": human_rel})
        elif deep:
            human_hashes[document_id] = sha256_file(human_path)

        digest = doha_hashes.get(document_id) or sha256_file(robot_path)
        content_groups[digest].append({
            "document_id": document_id,
            "collection_id": record.get("collection_id"),
            "current_status": record.get("current_status"),
            "robot_text_path": robot_rel,
        })
        if record.get("collection_id") != "doha_decisions":
            text = robot_path.read_text(encoding="utf-8", errors="replace")
            header = parse_authority_header(text)
            if header.get("header_tier") is not None and int(record["authority_tier"]) != int(header["header_tier"]):
                tier_conflicts.append({
                    "document_id": document_id,
                    "manifest_tier": int(record["authority_tier"]),
                    "header_tier": int(header["header_tier"]),
                    "robot_text_path": robot_rel,
                })

    duplicate_ids = [{"document_id": key, "lines": lines} for key, lines in id_lines.items() if len(lines) > 1]
    duplicate_content = [group for group in content_groups.values() if len(group) > 1]
    if duplicate_ids:
        warnings.append({"code": "duplicate_document_ids", "count": len(duplicate_ids), "sample": duplicate_ids[:20], "candidate_remediation": "assign unique proposed IDs and canonical duplicate links"})
    if duplicate_content:
        warnings.append({"code": "duplicate_robot_content", "groups": len(duplicate_content), "records": sum(len(g) for g in duplicate_content), "sample": duplicate_content[:10]})
    if tier_conflicts:
        warnings.append({"code": "authority_tier_conflicts", "count": len(tier_conflicts), "sample": tier_conflicts[:25]})
    unresolved_currency = statuses.get("current_or_verify", 0)
    if unresolved_currency:
        warnings.append({"code": "unresolved_currency", "count": unresolved_currency, "default_behavior": "exclude from controlling-answer indexes"})

    relationships = 0
    broken_relationships: list[dict[str, Any]] = []
    manifest_pairs = {(str(r.get("document_id")), norm(r.get("human_source_path")), norm(r.get("robot_text_path"))) for r in records}
    if relationships_path.is_file():
        for line_number, rel in iter_jsonl(relationships_path):
            relationships += 1
            pair = (str(rel.get("document_id")), norm(rel.get("human_source_path")), norm(rel.get("robot_text_path")))
            if pair not in manifest_pairs:
                broken_relationships.append({"line": line_number, "document_id": rel.get("document_id")})
    if broken_relationships:
        errors.append({"code": "broken_relationship_metadata", "count": len(broken_relationships), "sample": broken_relationships[:25]})

    index_results: list[dict[str, Any]] = []
    release_metadata_errors: list[str] = []
    modern_release = bool(entry.get("current_release") or entry.get("index_catalog"))
    index_paths = list(entry.get("local_indexes", []))
    if modern_release:
        try:
            catalog = read_json(bounded_path(root, entry["index_catalog"], ROBOT_PREFIX))
            index_paths = [item["production_path"] for item in catalog["indexes"]] + list(entry.get("doha_local_indexes", []))
            approved_release(root)
        except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
            release_metadata_errors.append(str(exc))
    for rel in index_paths:
        try:
            index_path = bounded_path(root, rel, "LOCAL_INDEXES/")
        except ValueError as exc:
            errors.append({"code": "index_path_boundary", "message": str(exc)})
            continue
        result: dict[str, Any] = {"path": norm(rel), "exists": index_path.is_file()}
        if result["exists"]:
            try:
                with contextlib.closing(sqlite3.connect(f"file:{index_path.as_posix()}?mode=ro", uri=True)) as conn:
                    result["integrity"] = conn.execute("PRAGMA integrity_check").fetchone()[0]
                    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    table = "corpus" if "corpus" in tables else "current_paths" if "current_paths" in tables else None
                    result["records"] = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] if table else None
            except sqlite3.Error as exc:
                result["integrity"] = "error"
                result["error"] = str(exc)
        if not result["exists"] or result.get("integrity") != "ok":
            errors.append({"code": "approved_index_failure", **result})
        index_results.append(result)

    # Consistency only: candidate validation recomputes every era from the text.
    doha_era_problems: list[str] = []
    if (root / doha_release.PATH_MANIFEST).is_file() and (root / doha_release.CONTENT).is_file():
        try:
            doha_era_problems = doha_release.check(root, root, recompute=False)
        except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
            doha_era_problems = [f"DOHA era check could not run: {exc}"]
    if doha_era_problems:
        warnings.append({"code": "doha_era_inconsistencies", "count": len(doha_era_problems), "sample": doha_era_problems[:10]})

    quality_blockers = {
        "duplicate_document_ids": len(duplicate_ids),
        "duplicate_content_groups": len(duplicate_content),
        "authority_tier_conflicts": len(tier_conflicts),
        "unresolved_currency": unresolved_currency,
        "doha_era_inconsistencies": len(doha_era_problems),
    }
    return {
        "schema_version": "1.0",
        "generated_utc": utc_now(),
        "library_root": str(root),
        "mode": "deep_hash" if deep else "read_only_metadata_and_robot_hash",
        "human_artifacts_used_as_answer_evidence": False,
        "summary": {
            "integrity_healthy": not errors,
            "production_response_ready": not errors and not release_metadata_errors and (modern_release or not any(quality_blockers.values())),
            "source_quality_complete": not any(quality_blockers.values()),
            "manifest_records": len(records),
            "relationships": relationships,
            "errors": len(errors),
            "warnings": len(warnings),
        },
        "status_counts": dict(statuses),
        "collection_counts": dict(collections_count),
        "quality_blockers": quality_blockers,
        "duplicate_document_ids": duplicate_ids,
        "duplicate_content_groups": duplicate_content,
        "authority_tier_conflicts": tier_conflicts,
        "human_hashes": human_hashes if deep else {},
        "approved_indexes": index_results,
        "release_metadata_errors": release_metadata_errors,
        "errors": errors,
        "warnings": warnings,
    }
