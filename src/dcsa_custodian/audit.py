from __future__ import annotations

import collections
import contextlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .authority import parse_authority_header
from .common import (HUMAN_PREFIX, ROBOT_PREFIX, decode_text, hash_workers, iter_jsonl, map_ordered, norm, read_json,
                     safe_relative, sha256_bytes, sha256_file, utc_now)
from . import doha_release, runcache
from .catalog import catalog_differences
from .release_contract import CATALOG, CONFIG, POINTER, POLICY, QUERY, ROUTER, STATE, approved_release, bounded_path


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


def _settled(path: Path) -> bool:
    """True when the database file alone is the database: no journal or write-ahead log beside it."""
    return not any(path.with_name(path.name + suffix).exists() for suffix in ("-wal", "-journal"))


def index_health(index_path: Path) -> dict[str, Any]:
    """``PRAGMA integrity_check`` and the row count of an index, once per run for the same bytes.

    The file is read and hashed on every call (unless ``release`` already read these
    bytes in this run); the check itself is repeated only when the bytes differ. A
    database with a journal or log beside it is always checked afresh.
    """
    def compute() -> dict[str, Any]:
        result: dict[str, Any] = {}
        try:
            with contextlib.closing(sqlite3.connect(f"file:{index_path.as_posix()}?mode=ro", uri=True)) as conn:
                result["integrity"] = conn.execute("PRAGMA integrity_check").fetchone()[0]
                tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                table = "corpus" if "corpus" in tables else "current_paths" if "current_paths" in tables else None
                result["records"] = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] if table else None
        except sqlite3.Error as exc:
            result["integrity"] = "error"
            result["error"] = str(exc)
        return result

    if not _settled(index_path):
        return compute()
    cache = runcache.current()
    try:
        digest = cache.sha256(index_path)
    except OSError:
        return compute()
    held = cache.peek("index_health", (sqlite3.sqlite_version, digest))
    if held is not None:
        cache.counts["index_health_reused"] += 1
        return dict(held)
    result = compute()
    if result.get("integrity") == "ok":  # only a pass is kept; a failure is always looked at again
        cache.result("index_health", (sqlite3.sqlite_version, digest), lambda: dict(result))
    return result


def approved_release_once(root: Path, check_integrity: bool = False) -> dict:
    """``approved_release(root)``, once per run for the same published bytes.

    The release contract is a pure function of the files it reads: both entry points,
    the seven metadata files, ``AGENTS.md``, every file the pointer binds by hash and
    every approved index. Those files are read and hashed here on every call (unless
    ``release`` already read these bytes in this run); when every hash equals an earlier
    passing call's, that call's result is returned. A failure is never kept, and a
    library this function cannot fingerprint goes straight to the contract.
    """
    cache = runcache.current()
    try:
        resolved = root.resolve()
        entry = read_json(resolved / "START_HERE_FOR_ROBOTS.json")
        pointer = read_json(resolved / POINTER)
        catalog = read_json(resolved / CATALOG)
        policy = read_json(resolved / POLICY)
        named = ["START_HERE_FOR_ROBOTS.json", "ROBOT_READABLE_DIRECTORY/START_HERE.json", POINTER, STATE, CATALOG, QUERY,
                 POLICY, CONFIG, ROUTER, "AGENTS.md", *sorted(pointer.get("metadata_sha256", {}))]
        indexes = [item["production_path"] for item in catalog["indexes"]] + \
            list(policy.get("content_access", {}).get("doha_approved_indexes", [])) + list(entry.get("doha_local_indexes", []))
        paths = [bounded_path(resolved, relative, "") for relative in dict.fromkeys(named + indexes)]
        if not all(path.is_file() for path in paths) or not all(_settled(path) for path in paths if path.suffix == ".sqlite"):
            return approved_release(root, check_integrity=check_integrity)
        key = (runcache.code_fingerprint(), check_integrity, tuple(zip(dict.fromkeys(named + indexes), cache.sha256_many(paths))))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return approved_release(root, check_integrity=check_integrity)
    held = cache.peek("approved_release", key)
    if held is None and not check_integrity:
        strict = cache.peek("approved_release", (key[0], True, key[2]))
        if strict is not None:
            # A pass with the integrity checks is a pass without them; the result is
            # reported exactly as the plain call reports it.
            held = {**strict, "index_checks": [{**item, "integrity": "not_requested"} for item in strict["index_checks"]]}
    if held is not None:
        cache.counts["approved_release_reused"] += 1
        return held
    compute = (lambda: _approved_release_with_integrity(root, catalog, policy)) if check_integrity else (lambda: approved_release(root))
    return cache.result("approved_release", key, compute)


def _approved_release_with_integrity(root: Path, catalog: dict, policy: dict) -> dict:
    """``approved_release(root, check_integrity=True)`` with each index's three integrity checks taken side by side.

    The contract runs first, without ``check_integrity``: every check it makes on the
    entry points, metadata, bound hashes and index contents. What ``check_integrity``
    adds is, for each approved index, ``PRAGMA integrity_check``, the file's SHA-256
    against the catalog and, for a DOHA index, against the access policy. Those three are
    made here with the contract's own error texts, on every index at once, and the
    integrity check of an index whose bytes this run has already checked is not repeated
    (``index_health``). ``tests/test_fast_path.py`` holds this equal to the contract, pass
    and fail.
    """
    health = approved_release(root)
    cache = runcache.current()
    resolved = root.resolve()
    listed = {item["production_path"]: item for item in catalog["indexes"]}
    doha_hashes = policy.get("content_access", {}).get("doha_index_sha256")

    def verify(check: dict) -> str | None:
        relative = check["path"]
        path = bounded_path(resolved, relative, "LOCAL_INDEXES/")
        if index_health(path).get("integrity") != "ok":
            return f"Approved index integrity failure: {relative}"
        item = listed.get(relative)
        if item and item.get("sha256") and cache.sha256(path) != item["sha256"]:
            return f"Approved index hash mismatch: {relative}"
        if doha_hashes is not None and relative in doha_hashes and cache.sha256(path) != doha_hashes[relative]:
            return f"Approved DOHA index hash mismatch: {relative}"
        return None

    for problem in map_ordered(verify, health["index_checks"]):
        if problem:
            raise ValueError(problem)
    return {**health, "index_checks": [{**check, "integrity": "ok"} for check in health["index_checks"]]}


ENRICHED = "ROBOT_READABLE_DIRECTORY/MANIFESTS/DOCUMENTS_ENRICHED.jsonl"
CHUNKS = "ROBOT_READABLE_DIRECTORY/CHUNKS/GENERAL_CITATION_SAFE_CHUNKS.jsonl"
GRAPH = "ROBOT_READABLE_DIRECTORY/WIKI/GRAPH.json"


def derived_agreement(root: Path, manifest_ids: set[str], index_paths: list[str],
                      pending_intake: set[str] | None = None) -> dict[str, Any]:
    """Do the published derived artifacts describe the documents `documents.jsonl` lists?

    Every reader gets its answers from the enriched manifest, the chunks, the navigation
    graph and the indexes, all built from the manifest at the last release. A manifest
    edited outside a release, or a derived file left behind by one, passes every
    per-record check; only comparing the ID sets shows it. `pending_intake` are IDs a
    staged intake has just added, which no derived artifact can hold yet.
    """
    pending = pending_intake or set()
    enriched_path = root / ENRICHED
    if not enriched_path.is_file():
        return {"checked": False, "agree": None, "reason": "no published enriched manifest", "artifacts": []}
    source_of: dict[str, str] = {}   # enriched ID -> the manifest ID it was derived from
    unchunked: set[str] = set()      # enriched IDs the chunk builder skips by rule
    robot_of: dict[str, str] = {}
    for _, row in iter_jsonl(enriched_path):
        identity = str(row["document_id"])
        source_of[identity] = str(row.get("source_document_id", identity))
        robot_of[identity] = str(row.get("robot_text_path", ""))
        if row.get("collection_id") == "doha_decisions" or row.get("duplicate_of"):
            unchunked.add(identity)
    enriched_sources = set(source_of.values())
    artifacts: list[dict[str, Any]] = []

    def record(path: str, ids: int, missing: set[str], stale: set[str], note: str | None = None) -> None:
        item: dict[str, Any] = {"artifact": path, "document_ids": ids, "missing": len(missing), "stale": len(stale)}
        if missing:
            item["missing_sample"] = sorted(missing)[:20]
        if stale:
            item["stale_sample"] = sorted(stale)[:20]
        if note:
            item["note"] = note
        artifacts.append(item)

    record(ENRICHED, len(source_of), manifest_ids - enriched_sources - pending, enriched_sources - manifest_ids)
    chunks_path = root / CHUNKS
    if chunks_path.is_file():
        chunked = {str(row["document_id"]) for _, row in iter_jsonl(chunks_path)}
        expected = {identity for identity, source in source_of.items()
                    if identity not in unchunked and source in manifest_ids}
        # A text with nothing but white space yields no chunk; only a text with content is missing.
        unchunked_with_text = set()
        for identity in expected - chunked:
            text_path = root / norm(robot_of[identity])
            if text_path.is_file() and text_path.read_text(encoding="utf-8", errors="replace").strip():
                unchunked_with_text.add(identity)
        record(CHUNKS, len(chunked), unchunked_with_text, {i for i in chunked if source_of.get(i) not in manifest_ids})
    else:
        record(CHUNKS, 0, set(), set(), "file missing")
    graph_path = root / GRAPH
    if graph_path.is_file():
        listed = {str(item.get("document_id")) for item in read_json(graph_path).get("documents", [])}
        record(GRAPH, len(listed), {i for i, source in source_of.items() if i not in listed and source in manifest_ids},
               {i for i in listed if source_of.get(i) not in manifest_ids})
    for relative in index_paths:
        try:
            index_path = bounded_path(root, relative, "LOCAL_INDEXES/")
            with contextlib.closing(sqlite3.connect(f"file:{index_path.as_posix()}?mode=ro", uri=True)) as conn:
                if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='documents'").fetchone():
                    continue
                indexed = {str(row[0]) for row in conn.execute("SELECT document_id FROM documents")}
        except (ValueError, sqlite3.Error):
            continue  # an unreadable index is already an approved_index_failure error
        # An index holds only the documents its rule admits, so only a stale ID is evidence.
        record(norm(relative), len(indexed), set(), {i for i in indexed if source_of.get(i) not in manifest_ids})
    return {"checked": True, "agree": not any(item["missing"] or item["stale"] for item in artifacts),
            "pending_intake": len(pending), "artifacts": artifacts}


def audit_library(root: Path, deep: bool = False, pending_doha: set[str] | None = None,
                  pending_intake: set[str] | None = None) -> dict[str, Any]:
    entry_path = root / "START_HERE_FOR_ROBOTS.json"
    if not entry_path.is_file():
        raise FileNotFoundError(entry_path)
    entry = read_json(entry_path)
    manifest_path = root / norm(entry["documents"])
    relationships_path = root / norm(entry["relationships"])
    doha_hashes, _ = _doha_hashes(root)

    records: list[dict[str, Any]] = []
    id_lines: dict[str, list[int]] = collections.defaultdict(list)
    statuses: collections.Counter[str] = collections.Counter()
    collections_count: collections.Counter[str] = collections.Counter()

    # Pass 1, in manifest order and without touching a file: the checks on the row itself.
    # Each row becomes either the error it raised or a job for the file checks.
    rows: list[tuple[str, Any]] = []
    for line_number, record in iter_jsonl(manifest_path):
        records.append(record)
        missing = sorted(REQUIRED_FIELDS - record.keys())
        if missing:
            rows.append(("error", {"code": "manifest_missing_fields", "line": line_number, "fields": missing}))
            continue
        document_id = str(record["document_id"])
        id_lines[document_id].append(line_number)
        statuses[str(record.get("current_status"))] += 1
        collections_count[str(record.get("collection_id"))] += 1
        try:
            robot_rel = safe_relative(record["robot_text_path"], ROBOT_PREFIX)
            human_rel = safe_relative(record["human_source_path"], HUMAN_PREFIX)
        except ValueError as exc:
            rows.append(("error", {"code": "path_boundary", "line": line_number, "document_id": document_id, "message": str(exc)}))
            continue
        rows.append(("job", (line_number, record, document_id, robot_rel, human_rel)))

    # The checks that do not depend on the per-record file checks start now and run beside
    # them: the release contract, each index's integrity, the derived-artifact comparison
    # and the DOHA store consistency. Each is the same call as before; its outcome is
    # taken up below at the point the serial audit reached it, so the report (and the
    # order of its errors and warnings) is the same. With one worker they run there.
    release_metadata_errors: list[str] = []
    modern_release = bool(entry.get("current_release") or entry.get("index_catalog"))
    index_paths = list(entry.get("local_indexes", []))
    background = ThreadPoolExecutor(max_workers=4) if hash_workers() > 1 else None

    def start(function: Any, *arguments: Any) -> Any:
        return background.submit(function, *arguments) if background else _Later(function, arguments)

    def check_index(rel: str) -> tuple[str, dict[str, Any]]:
        try:
            index_path = bounded_path(root, rel, "LOCAL_INDEXES/")
        except ValueError as exc:
            return "boundary", {"code": "index_path_boundary", "message": str(exc)}
        result: dict[str, Any] = {"path": norm(rel), "exists": index_path.is_file()}
        if result["exists"]:
            result.update(index_health(index_path))
        return "result", result

    def doha_consistency() -> list[str]:
        # Consistency only: candidate validation recomputes every era from the text.
        if not ((root / doha_release.PATH_MANIFEST).is_file() and (root / doha_release.CONTENT).is_file()):
            return []
        try:
            return doha_release.check(root, root, recompute=False, pending=pending_doha)
        except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
            return [f"DOHA era check could not run: {exc}"]

    try:
        contract = None
        if modern_release:
            try:
                catalog = read_json(bounded_path(root, entry["index_catalog"], ROBOT_PREFIX))
                index_paths = [item["production_path"] for item in catalog["indexes"]] + list(entry.get("doha_local_indexes", []))
                contract = start(approved_release_once, root)
            except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
                release_metadata_errors.append(str(exc))
        index_checks = start(map_ordered, check_index, index_paths)
        derived_check = start(derived_agreement, root, set(id_lines), index_paths, pending_intake)
        doha_check = start(doha_consistency)
        return _audit_records(root, deep, entry, rows, records, id_lines, statuses, collections_count, doha_hashes,
                              relationships_path, pending_doha, modern_release, release_metadata_errors,
                              contract, index_checks, derived_check, doha_check)
    finally:
        if background:
            background.shutdown(wait=True)


class _Later:
    """A call made when its result is asked for: the serial audit's order, for one worker."""

    def __init__(self, function: Any, arguments: tuple) -> None:
        self.function, self.arguments = function, arguments

    def result(self) -> Any:
        return self.function(*self.arguments)


def _audit_records(root: Path, deep: bool, entry: dict[str, Any], rows: list[tuple[str, Any]], records: list[dict[str, Any]],
                   id_lines: dict[str, list[int]], statuses: collections.Counter, collections_count: collections.Counter,
                   doha_hashes: dict[str, str], relationships_path: Path, pending_doha: set[str] | None,
                   modern_release: bool, release_metadata_errors: list[str], contract: Any, index_checks: Any,
                   derived_check: Any, doha_check: Any) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    content_groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    tier_conflicts: list[dict[str, Any]] = []
    human_hashes: dict[str, str] = {}

    # Pass 2, on every core: existence, the human hash (deep), the robot hash and header.
    # The same files are read as before, each once; only the order of reading changes.
    cache = runcache.current()

    def inspect(row: tuple[str, Any]) -> dict[str, Any] | None:
        if row[0] != "job":
            return None
        _, record, document_id, robot_rel, human_rel = row[1]
        robot_path, human_path = root / robot_rel, root / human_rel
        if not robot_path.is_file():
            return {"missing_robot": True}
        found: dict[str, Any] = {"missing_human": not human_path.is_file()}
        if deep and not found["missing_human"]:
            found["human_sha256"] = cache.sha256(human_path)
        digest = doha_hashes.get(document_id)
        if record.get("collection_id") != "doha_decisions":
            token, held = cache.lookup(robot_path)
            header = cache.peek("authority_header", held) if held else None
            if header is None:
                data = robot_path.read_bytes()
                held = sha256_bytes(data)
                cache.store(token, held)
                header = cache.result("authority_header", held, lambda: parse_authority_header(decode_text(data)))
            found["header"] = header
            digest = digest or held
        found["digest"] = digest or cache.sha256(robot_path)
        return found

    # Pass 3, in manifest order again: the report is assembled exactly as a serial loop would.
    for row, found in zip(rows, map_ordered(inspect, rows)):
        if row[0] == "error":
            errors.append(row[1])
            continue
        line_number, record, document_id, robot_rel, human_rel = row[1]
        if found.get("missing_robot"):
            errors.append({"code": "missing_robot", "line": line_number, "document_id": document_id, "path": robot_rel})
            continue
        if found["missing_human"]:
            errors.append({"code": "missing_human_parity_artifact", "line": line_number, "document_id": document_id, "path": human_rel})
        elif deep:
            human_hashes[document_id] = found["human_sha256"]
        content_groups[found["digest"]].append({
            "document_id": document_id,
            "collection_id": record.get("collection_id"),
            "current_status": record.get("current_status"),
            "robot_text_path": robot_rel,
        })
        if record.get("collection_id") != "doha_decisions":
            header = found["header"]
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
    repeated_relationships: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str, str]] = set()
    manifest_pairs = {(str(r.get("document_id")), norm(r.get("human_source_path")), norm(r.get("robot_text_path"))) for r in records}
    if relationships_path.is_file():
        for line_number, rel in iter_jsonl(relationships_path):
            relationships += 1
            pair = (str(rel.get("document_id")), norm(rel.get("human_source_path")), norm(rel.get("robot_text_path")))
            if pair not in manifest_pairs:
                broken_relationships.append({"line": line_number, "document_id": rel.get("document_id")})
            elif pair in seen_pairs:
                repeated_relationships.append({"line": line_number, "document_id": rel.get("document_id")})
            seen_pairs.add(pair)
    if repeated_relationships:
        # Harmless to readers, but it is why the relationship count can exceed the record count.
        warnings.append({"code": "duplicate_relationship_rows", "count": len(repeated_relationships), "sample": repeated_relationships[:25]})
    if broken_relationships:
        errors.append({"code": "broken_relationship_metadata", "count": len(broken_relationships), "sample": broken_relationships[:25]})

    index_results: list[dict[str, Any]] = []
    if contract is not None:
        try:
            contract.result()
        except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
            release_metadata_errors.append(str(exc))

    # Each index is checked in full, as before; the indexes are checked side by side.
    for kind, result in index_checks.result():
        if kind == "boundary":
            errors.append(result)
            continue
        if not result["exists"] or result.get("integrity") != "ok":
            errors.append({"code": "approved_index_failure", **result})
        index_results.append(result)

    # Reported, not blocking: the remedy for drift is a candidate build, which this audit gates.
    derived = derived_check.result()
    if derived["agree"] is False:
        warnings.append({"code": "derived_artifact_drift",
                         "count": sum(item["missing"] + item["stale"] for item in derived["artifacts"]),
                         "artifacts": [item for item in derived["artifacts"] if item["missing"] or item["stale"]],
                         "meaning": "published derived artifacts and documents.jsonl disagree on the documents held: "
                                    "a manifest edited outside a release, or a stale derived file",
                         "remedy": "build, validate, evaluate and publish a candidate; never edit either side by hand"})
    catalog_report: dict[str, Any] = {"checked": False, "agree": None, "differences": []}
    if entry.get("catalog"):
        try:
            catalog_path = bounded_path(root, entry["catalog"], ROBOT_PREFIX)
            differences = catalog_differences(read_json(catalog_path), records)
            catalog_report = {"checked": True, "agree": not differences, "path": norm(entry["catalog"]), "differences": differences}
        except (OSError, ValueError) as exc:
            catalog_report = {"checked": True, "agree": False, "path": norm(entry["catalog"]), "differences": [], "error": str(exc)}
        if not catalog_report["agree"]:
            warnings.append({"code": "collection_catalog_drift", "count": len(catalog_report["differences"]) or 1,
                             "sample": catalog_report["differences"][:10],
                             "remedy": "the next candidate build regenerates the catalog from the manifest"})

    doha_era_problems: list[str] = doha_check.result()
    if pending_doha:
        # Staged by this intake build; the build assigns their era and candidate
        # validation checks them with every other decision.
        warnings.append({"code": "doha_era_pending_intake", "count": len(pending_doha)})
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
            # None when the library has no published derived artifacts to compare.
            "derived_artifacts_agree": derived["agree"],
            "collection_catalog_agrees": catalog_report["agree"],
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
        "derived_artifacts": derived,
        "collection_catalog": catalog_report,
        "release_metadata_errors": release_metadata_errors,
        "errors": errors,
        "warnings": warnings,
    }
