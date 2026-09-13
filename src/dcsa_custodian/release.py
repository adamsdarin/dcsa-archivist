from __future__ import annotations

import collections
import contextlib
import json
import os
import shutil
import sqlite3
import tempfile
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .audit import audit_library
from .chunks import build_chunks
from .common import HUMAN_PREFIX, ROBOT_PREFIX, iter_jsonl, norm, read_json, sha256_file, sha256_text, utc_now, write_json, write_jsonl
from .decisions import apply_metadata_decisions, load_metadata_decisions
from .directive_splits import build_directive_splits
from .enrich import enrich_manifest
from .evals import evaluate_candidate
from .indexes import build_indexes
from .semantic import MODEL_NAME, VECTOR_DIM, embed_texts
from .events import build_changes, reconcile_event
from .wiki import build_graph, lint_report
from .intake import stage_intake
from .release_contract import STATE, POINTER, CATALOG, QUERY, CONFIG, POLICY, ROUTER, approved_release


def release_id_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _variance_markdown(audit: dict[str, Any], records: list[dict[str, Any]], chunks: list[dict[str, Any]], catalog: list[dict[str, Any]]) -> str:
    eligibility = collections.Counter(record["answer_eligibility"] for record in records)
    roles = collections.Counter(record["authority_role"] for record in records)
    lines = [
        "# DCSA Library Custodian variance report",
        "",
        f"Generated: `{utc_now()}`",
        "",
        "## Production findings",
        "",
        f"- Duplicate document IDs: **{audit['quality_blockers']['duplicate_document_ids']}**",
        f"- Duplicate robot-content groups: **{audit['quality_blockers']['duplicate_content_groups']}**",
        f"- Authority tier conflicts: **{audit['quality_blockers']['authority_tier_conflicts']}**",
        f"- Currency-unresolved records: **{audit['quality_blockers']['unresolved_currency']}**",
        "",
        "## Candidate remediation",
        "",
        "- Assigns unique proposed IDs and canonical duplicate links.",
        "- Excludes identical duplicate content from answer indexes.",
        "- Uses authority roles and role priorities instead of conflicting embedded tiers.",
        "- Excludes unresolved currency from controlling-answer indexes.",
        "- Produces citation-safe chunks with stable locators and exact-source hashes.",
        "- Separates contractor-controlling authority, Government issuances, guidance, context, unresolved, and historical indexes.",
        "- Preserves human paths as unindexed citation metadata.",
        "",
        "## Candidate counts",
        "",
        f"- Enriched documents: **{len(records)}**",
        f"- Citation-safe chunks: **{len(chunks)}**",
    ]
    for key, value in sorted(eligibility.items()):
        lines.append(f"- Eligibility `{key}`: **{value}**")
    lines.extend(["", "## Authority roles", ""])
    for key, value in sorted(roles.items(), key=lambda item: (item[0])):
        lines.append(f"- `{key}`: **{value}**")
    lines.extend(["", "## Candidate indexes", ""])
    for item in catalog:
        lines.append(f"- `{item['path']}` — {item['documents']} documents / {item['chunks']} chunks; default allowed: `{str(item['default_allowed']).lower()}`")
    lines.extend([
        "",
        "## Publication blockers",
        "",
        "The candidate must not replace the production default retrieval route until currency-unresolved controlling sources are reviewed and the candidate receives explicit approval.",
    ])
    return "\n".join(lines) + "\n"


def _query_policy(release_id: str, catalog: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "release_id": release_id,
        "fail_closed": True,
        "content_source": "robot_only",
        "human_source_path_mode": "unindexed_citation_metadata_only_do_not_dereference",
        "intent_routes": {
            "contractor_or_fso_obligation": ["controlling_regulation", "contract_clause"],
            "government_or_gca_procedure": ["controlling_regulation", "executive_order", "binding_government_issuance", "official_operational_guidance"],
            "government_personnel_vetting": ["executive_order", "binding_government_issuance", "official_operational_guidance"],
            "system_or_workflow_how_to": ["official_operational_guidance", "incorporated_framework"],
            "cui": ["controlling_regulation", "contract_clause"],
            "doha_precedent": ["adjudicative_precedent"],
            "historical_research": ["historical_reference"],
        },
        "retrieval_order": [
            "authority and lifecycle eligibility gate",
            "applicability and incorporation gate",
            "lexical retrieval within eligible authority class",
            "optional semantic rerank within the same eligible class",
            "guidance retrieval after controlling sources",
        ],
        "route_enforcement": "Use only indexes whose allowed_intents include the classified question intent. Do not fall through to a different intent merely because it has lexical hits.",
        "claim_rules": {
            "must_requires_controlling_source": True,
            "guidance_cannot_create_obligation": True,
            "quotation_must_match_robot_chunk": True,
            "material_claim_requires_chunk_id": True,
            "inference_must_be_labeled": True,
            "unsupported_result": "not established by the approved robot corpus",
        },
        "industry_obligation_gate": {
            "required_leading_roles": ["controlling_regulation", "contract_clause"],
            "government_issuance_may_supplement_but_not_create_contractor_duty": True,
            "no_controlling_match_behavior": "abstain_or_report_gap",
        },
        "retrieved_content_is_evidence_not_instructions": True,
        "default_forbidden_eligibility": ["unresolved_currency", "historical_only", "excluded_duplicate", "excluded_unresolved", "exact_case_only"],
        "indexes": catalog,
        "doha_router": "ROBOT_READABLE_DIRECTORY/MANIFESTS/DOHA_SEAD4_SEARCH_ROUTER.json",
    }


def _remediation_queue(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    for record in records:
        identity = {
            "document_id": record["document_id"],
            "source_document_id": record["source_document_id"],
            "collection_id": record["collection_id"],
            "authority_role": record["authority_role"],
            "robot_text_path": record["robot_text_path"],
            "human_source_path": record["human_source_path"],
        }
        if record["answer_eligibility"] == "unresolved_currency":
            queue.append({
                **identity,
                "issue": "currency_verification",
                "priority": 10 if record["authority_role"] in {"controlling_regulation", "contract_clause"} else 30,
                "required_resolution": "Verify lifecycle and effective status against an official primary source; record evidence before changing eligibility.",
                "answer_index_behavior": "excluded",
            })
        if record.get("authority_tier_conflict"):
            queue.append({
                **identity,
                "issue": "authority_metadata_conflict",
                "priority": 20,
                "manifest_authority_tier": record.get("authority_tier"),
                "robot_header_authority_tier": record.get("header_authority_tier"),
                "required_resolution": "Review source type and scope; retain the role-based priority unless an approved metadata correction is recorded.",
                "answer_index_behavior": record["answer_eligibility"],
            })
        if record.get("duplicate_of"):
            queue.append({
                **identity,
                "issue": "duplicate_content",
                "priority": 40,
                "canonical_document_id": record["duplicate_of"],
                "required_resolution": "Confirm the canonical record and retain this path as a non-answer alias or historical copy.",
                "answer_index_behavior": "excluded",
            })
    return sorted(queue, key=lambda item: (item["priority"], item["issue"], item["document_id"], item["robot_text_path"]))


def build_candidate(project_root: Path, root: Path, config: dict[str, Any], release_id: str | None = None, deep: bool = False, intake_plan: Path | None = None) -> dict[str, Any]:
    if intake_plan is not None:
        audit = audit_library(root, deep=True)
        if audit["errors"]:
            raise RuntimeError("production audit failed before intake staging")
        state_root = project_root / config.get("state_directory", ".custodian")
        state_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="intake-", dir=state_root) as temporary:
            staged = Path(temporary) / "library"
            changed = stage_intake(root.resolve(), staged, intake_plan.resolve())
            return _build_candidate(project_root, staged, config, release_id, True, changed, root)
    return _build_candidate(project_root, root, config, release_id, deep)


def _build_candidate(project_root: Path, root: Path, config: dict[str, Any], release_id: str | None = None, deep: bool = False,
                     source_files: list[str] | None = None, target_root: Path | None = None) -> dict[str, Any]:
    release_id = release_id or release_id_now()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", release_id):
        raise ValueError("invalid release ID")
    state_root = project_root / config.get("state_directory", ".custodian")
    release_dir = state_root / "releases" / release_id
    if release_dir.exists():
        raise FileExistsError(f"release already exists: {release_id}")
    release_dir.mkdir(parents=True)
    for relative in source_files or []:
        target = release_dir / "production" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, target)

    audit = audit_library(root, deep=deep)
    if audit["errors"]:
        raise RuntimeError(f"production integrity audit failed with {len(audit['errors'])} blocking errors")
    write_json(release_dir / "reports/PRODUCTION_AUDIT.json", audit)

    entry = read_json(root / "START_HERE_FOR_ROBOTS.json")
    manifest_path = root / norm(entry["documents"])
    records = enrich_manifest(root, manifest_path, audit.get("human_hashes"))
    decisions_path = project_root / config.get("metadata_decisions_file", "decisions/metadata_decisions.json")
    metadata_decisions = load_metadata_decisions(decisions_path)
    metadata_decisions_applied = apply_metadata_decisions(records, metadata_decisions)
    write_json(release_dir / "reports/APPLIED_METADATA_DECISIONS.json", {
        "schema_version": "1.0",
        "source": str(decisions_path),
        "applied": metadata_decisions_applied,
        "decisions": metadata_decisions,
    })
    enriched_path = release_dir / "production/ROBOT_READABLE_DIRECTORY/MANIFESTS/DOCUMENTS_ENRICHED.jsonl"
    write_jsonl(enriched_path, records)
    remediation_queue = _remediation_queue(records)
    write_jsonl(release_dir / "reports/REMEDIATION_QUEUE.jsonl", remediation_queue)

    directive_split_files, directive_split_problems, directive_split_skipped = build_directive_splits(root, records)
    for item in directive_split_files:
        write_text = release_dir / "production" / item["relative_path"]
        write_text.parent.mkdir(parents=True, exist_ok=True)
        write_text.write_text(item["content"], encoding="utf-8", newline="\n")
    write_json(release_dir / "reports/DIRECTIVE_SPLIT_REPORT.json", {
        "schema_version": "1.0",
        "files_written": len(directive_split_files),
        "problems": directive_split_problems,
        "skipped": directive_split_skipped,
    })

    chunks = build_chunks(
        root, records,
        int(config.get("default_chunk_characters", 3200)),
        int(config.get("maximum_chunk_characters", 4800)),
        int(config.get("chunk_overlap_characters", 300)),
    )
    chunks_path = release_dir / "production/ROBOT_READABLE_DIRECTORY/CHUNKS/GENERAL_CITATION_SAFE_CHUNKS.jsonl"
    write_jsonl(chunks_path, chunks)
    write_json(release_dir / "reports/RELEASE_CHANGES.json", build_changes(root, records, chunks, release_id))
    write_json(release_dir / "production/ROBOT_READABLE_DIRECTORY/WIKI/GRAPH.json", {
        "schema_version": "1.0", "release_id": release_id, "use": "navigation_only_not_answer_evidence",
        "graph": build_graph(records),
        "documents": [{key: r.get(key) for key in ("document_id", "title", "robot_text_path", "human_source_path", "answer_eligibility")} for r in records],
    })
    write_json(release_dir / "reports/WIKI_LINT.json", lint_report(records, f"candidate:{release_id}"))

    embedded_vectors = embed_texts([chunk["content"] for chunk in chunks])
    chunk_vectors = {chunk["chunk_id"]: vector for chunk, vector in zip(chunks, embedded_vectors)}

    indexes_dir = release_dir / "indexes"
    catalog = build_indexes(indexes_dir, records, chunks, chunk_vectors, MODEL_NAME, VECTOR_DIM)
    for item in catalog:
        item["production_path"] = f"LOCAL_INDEXES/CUSTODIAN/{release_id}/{Path(item['path']).name}"
    query_policy = _query_policy(release_id, catalog)
    write_json(release_dir / "production/ROBOT_READABLE_DIRECTORY/RETRIEVAL/INDEX_CATALOG.json", {
        "schema_version": "1.0", "release_id": release_id, "indexes": catalog,
        "default_sequence": [item["production_path"] for item in catalog if item["default_allowed"]],
    })
    write_json(release_dir / "production/ROBOT_READABLE_DIRECTORY/RETRIEVAL/QUERY_POLICY.json", query_policy)

    eligibility = collections.Counter(record["answer_eligibility"] for record in records)
    controlling_index = next(
        (item for item in catalog if Path(item["path"]).name == "DCSA_CONTROLLING_AUTHORITY_CHUNKS_FTS.sqlite"),
        None,
    )
    publication_blockers: list[str] = []
    if not controlling_index or not controlling_index["chunks"]:
        publication_blockers.append(
            "no verified current controlling regulation or contract-clause chunks are available for contractor-obligation answers"
        )
    for problem in directive_split_problems:
        publication_blockers.append(f"directive split: {problem}")
    state = {
        "schema_version": "1.0",
        "release_id": release_id,
        "release_status": "candidate_unapproved",
        "generated_utc": utc_now(),
        "library_root_at_build": str((target_root or root).resolve()),
        "source_intake_files": source_files or [],
        "production_integrity_healthy": audit["summary"]["integrity_healthy"],
        "production_response_ready": audit["summary"]["production_response_ready"],
        "candidate_response_ready": not publication_blockers,
        "candidate_publishable": not publication_blockers,
        "publication_blockers": publication_blockers,
        "manifest_records": len(records),
        "citation_safe_chunks": len(chunks),
        "directive_split_files": len(directive_split_files),
        "directive_split_problems": directive_split_problems,
        "answer_eligibility_counts": dict(eligibility),
        "parity": {"relationships": audit["summary"]["manifest_records"], "broken": 0, "human_hash_mode": "deep" if deep else "existence_and_size"},
        "quality_blockers": audit["quality_blockers"],
        "remediation_queue_items": len(remediation_queue),
        "metadata_decisions_applied": metadata_decisions_applied,
        "approved_indexes": [],
        "candidate_indexes": catalog,
        "requires_human_approval": False,
    }
    write_json(release_dir / "production/ROBOT_READABLE_DIRECTORY/STATE/LIBRARY_STATE.json", state)
    (release_dir / "reports/VARIANCE_REPORT.md").parent.mkdir(parents=True, exist_ok=True)
    (release_dir / "reports/VARIANCE_REPORT.md").write_text(_variance_markdown(audit, records, chunks, catalog), encoding="utf-8", newline="\n")
    evaluation = evaluate_candidate(release_dir, project_root / "evals/golden_queries.json")
    write_json(release_dir / "reports/RETRIEVAL_EVALUATION.json", evaluation)
    manifest_files = []
    for path in sorted(p for p in release_dir.rglob("*") if p.is_file()):
        manifest_files.append({"path": path.relative_to(release_dir).as_posix(), "sha256": sha256_file(path), "bytes": path.stat().st_size})
    release_manifest = {
        "schema_version": "1.0", "release_id": release_id, "status": "candidate_unapproved",
        "created_utc": utc_now(), "files": manifest_files,
    }
    write_json(release_dir / "RELEASE_MANIFEST.json", release_manifest)
    validation = validate_candidate(root, release_dir)
    write_json(release_dir / "VALIDATION.json", validation)
    return {"release_id": release_id, "release_directory": str(release_dir), "validation": validation, "state": state}


def validate_candidate(root: Path, release_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    manifest_path = release_dir / "RELEASE_MANIFEST.json"
    if not manifest_path.is_file():
        return {"valid": False, "errors": ["missing RELEASE_MANIFEST.json"]}
    manifest = read_json(manifest_path)
    for item in manifest["files"]:
        path = release_dir / item["path"]
        if not path.is_file() or sha256_file(path) != item["sha256"]:
            errors.append(f"release file hash mismatch: {item['path']}")
    evaluation_path = release_dir / "reports/RETRIEVAL_EVALUATION.json"
    if not evaluation_path.is_file() or not read_json(evaluation_path).get("passed"):
        errors.append("retrieval evaluation missing or failed")
    state_path = release_dir / "production/ROBOT_READABLE_DIRECTORY/STATE/LIBRARY_STATE.json"
    state = read_json(state_path) if state_path.is_file() else {}
    publication_blockers = list(state.get("publication_blockers", []))

    enriched_path = release_dir / "production/ROBOT_READABLE_DIRECTORY/MANIFESTS/DOCUMENTS_ENRICHED.jsonl"
    records = [record for _, record in iter_jsonl(enriched_path)]
    ids = [record["document_id"] for record in records]
    if len(ids) != len(set(ids)):
        errors.append("candidate contains duplicate document IDs")
    for record in records:
        if not norm(record.get("robot_text_path")).startswith(ROBOT_PREFIX):
            errors.append(f"robot path outside root: {record.get('document_id')}")
        if not norm(record.get("human_source_path")).startswith(HUMAN_PREFIX):
            errors.append(f"human citation path outside root: {record.get('document_id')}")
        if record.get("current_status") == "current" and record.get("authority_role") == "unclassified_role":
            errors.append(f"current record has unclassified authority role: {record.get('document_id')}")
        if record.get("duplicate_of") and record.get("answer_eligibility") != "excluded_duplicate":
            errors.append(f"duplicate not excluded: {record.get('document_id')}")

    chunks_path = release_dir / "production/ROBOT_READABLE_DIRECTORY/CHUNKS/GENERAL_CITATION_SAFE_CHUNKS.jsonl"
    source_cache: dict[str, str] = {}
    chunk_count = 0
    for _, chunk in iter_jsonl(chunks_path):
        chunk_count += 1
        robot_rel = norm(chunk["robot_text_path"])
        if robot_rel not in source_cache:
            staged_source = release_dir / "production" / robot_rel
            source_cache[robot_rel] = (staged_source if staged_source.is_file() else root / robot_rel).read_text(encoding="utf-8", errors="replace")
        if chunk["content"] not in source_cache[robot_rel]:
            errors.append(f"chunk not found verbatim in robot source: {chunk['chunk_id']}")
        if sha256_text(chunk["content"]) != chunk["content_sha256"]:
            errors.append(f"chunk hash mismatch: {chunk['chunk_id']}")
        if len(errors) > 100:
            break

    split_report_path = release_dir / "reports/DIRECTIVE_SPLIT_REPORT.json"
    if split_report_path.is_file():
        split_report = read_json(split_report_path)
        for problem in split_report.get("problems", []):
            errors.append(f"directive split: {problem}")
    for directive, out_dir in (("SEAD-3", "SEAD-3_Reporting-Requirements"),
                                ("SEAD-4", "SEAD-4_Adjudicative-Guidelines"),
                                ("ISL-2021-02", "2021-02_SEAD-3_rev-2024")):
        split_manifest_path = None
        for candidate in (release_dir / "production").rglob(f"{out_dir}/manifest.json"):
            split_manifest_path = candidate
            break
        if split_manifest_path is None:
            continue  # already recorded as a problem above, or the directive was unaffected
        split_manifest = read_json(split_manifest_path)
        for section in split_manifest.get("sections", []):
            section_path = split_manifest_path.parent / section["file"]
            if not section_path.is_file():
                errors.append(f"{directive}: {section['file']} listed in manifest.json but not written")
                continue
            body = section_path.read_text(encoding="utf-8").split("---\n\n", 1)[-1].rstrip("\n")
            if sha256_text(body) != section["body_sha256"]:
                errors.append(f"{directive}: {section['file']} body hash does not match manifest.json")

    index_results = []
    for index_path in sorted((release_dir / "indexes").glob("*.sqlite")):
        with contextlib.closing(sqlite3.connect(f"file:{index_path.as_posix()}?mode=ro", uri=True)) as conn:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            count = conn.execute("SELECT count(*) FROM corpus").fetchone()[0]
            if integrity != "ok":
                errors.append(f"index integrity failure: {index_path.name}")
            bad_paths = conn.execute("SELECT count(*) FROM corpus WHERE robot_text_path NOT LIKE 'ROBOT_READABLE_DIRECTORY/%' OR human_source_path NOT LIKE 'HUMAN_READABLE_DIRECTORY/%'").fetchone()[0]
            if bad_paths:
                errors.append(f"index path boundary failure: {index_path.name} ({bad_paths})")
            vector_count = conn.execute("SELECT count(*) FROM vectors").fetchone()[0]
            if vector_count != count:
                errors.append(f"vector coverage mismatch: {index_path.name} ({vector_count} vectors for {count} chunks)")
            orphan_vectors = conn.execute("SELECT count(*) FROM vectors WHERE chunk_id NOT IN (SELECT chunk_id FROM corpus)").fetchone()[0]
            if orphan_vectors:
                errors.append(f"orphaned vectors with no corpus chunk: {index_path.name} ({orphan_vectors})")
            index_results.append({"path": index_path.name, "integrity": integrity, "chunks": count, "vectors": vector_count})
    valid = not errors
    return {
        "schema_version": "1.0",
        "validated_utc": utc_now(),
        "valid": valid,
        "publishable": valid and not publication_blockers,
        "errors": errors,
        "publication_blockers": publication_blockers,
        "documents": len(records),
        "chunks": chunk_count,
        "indexes": index_results,
    }


def approve_candidate(release_dir: Path, approved_by: str, note: str) -> dict[str, Any]:
    validation = read_json(release_dir / "VALIDATION.json")
    if not validation.get("valid"):
        raise RuntimeError("cannot approve an invalid candidate")
    if not validation.get("publishable"):
        raise RuntimeError(f"cannot approve an unpublishable candidate: {validation.get('publication_blockers', [])}")
    receipt = {
        "schema_version": "1.0", "release_id": release_dir.name, "approved_utc": utc_now(),
        "approved_by": approved_by, "note": note, "scope": "derived_artifacts_only",
    }
    write_json(release_dir / "APPROVAL.json", receipt)
    return receipt


def publish_candidate(project_root: Path, root: Path, config: dict[str, Any], release_dir: Path, dry_run: bool = False) -> dict[str, Any]:
    validation = validate_candidate(root, release_dir)
    if not validation["valid"]:
        raise RuntimeError("candidate validation failed")
    if not validation["publishable"]:
        raise RuntimeError(f"candidate is not publishable: {validation.get('publication_blockers', [])}")
    # An old passing report must not bypass stronger current acceptance cases.
    fresh_evaluation = evaluate_candidate(release_dir, project_root / "evals/golden_queries.json")
    if not fresh_evaluation["passed"]:
        raise RuntimeError("candidate fails the current retrieval evaluation; build a corrected candidate")
    approval_path = release_dir / "APPROVAL.json"
    if not approval_path.is_file():
        write_json(approval_path, {
            "schema_version": "1.0", "release_id": release_dir.name, "approved_utc": utc_now(),
            "approved_by": "autonomous-pipeline", "note": "auto-approved: validation and retrieval evaluation passed with no publication blockers",
            "scope": "source_intake_and_derived" if read_json(release_dir / "production" / STATE).get("source_intake_files") else "derived_artifacts_only",
        })
    release_id = release_dir.name
    changes_path = release_dir / "reports/RELEASE_CHANGES.json"
    changes = read_json(changes_path)
    current_id = read_json(root / POINTER).get("release_id") if (root / POINTER).is_file() else None
    if current_id not in (changes["previous_release_id"], release_id):
        raise RuntimeError("library advanced since this candidate was built; rebuild against the current release")
    approval = read_json(approval_path)
    if approval.get("release_id") != release_id:
        raise RuntimeError("approval receipt does not match the candidate release")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    rollback_dir = project_root / config.get("state_directory", ".custodian") / "rollback" / timestamp
    copied: list[str] = []
    snapshots: list[str] = []
    production_root = release_dir / "production"
    # Candidate artifacts remain immutable. Publication metadata is a separately
    # staged, reproducible overlay, never a copy of candidate_unapproved state.
    overlay = release_dir / "publication" / timestamp
    catalog = read_json(production_root / CATALOG)
    for item in catalog["indexes"]:
        item["sha256"] = sha256_file(release_dir / item["path"])
    query = read_json(production_root / QUERY)
    query["indexes"] = catalog["indexes"]
    state = read_json(production_root / STATE)
    if Path(state["library_root_at_build"]).resolve() != root.resolve():
        raise ValueError("candidate was built for another library root")
    published_utc = utc_now()
    state.update({"release_status": "published", "production_integrity_healthy": True,
                  "production_response_ready": True, "approved_indexes": catalog["indexes"],
                  "candidate_indexes": [], "approval": approval, "published_utc": published_utc,
                  "readiness_scope": "validated approved indexes with unresolved and historical material excluded from default retrieval"})
    for relative, value in ((CATALOG, catalog), (QUERY, query), (STATE, state)):
        write_json(overlay / relative, value)
    entry = read_json(root / "START_HERE_FOR_ROBOTS.json")
    doha = ["LOCAL_INDEXES/DOHA_CASE_TOPICS_FTS.sqlite", "LOCAL_INDEXES/DOHA_CURRENT_PATHS.sqlite"]
    entry.pop("local_indexes", None)
    entry.update({"current_release": POINTER, "library_state": STATE, "index_catalog": CATALOG,
                  "query_policy": QUERY, "access_policy": POLICY, "retrieval": CONFIG,
                  "doha_router": ROUTER, "doha_local_indexes": doha})
    entry["navigation_wiki"] = "ROBOT_READABLE_DIRECTORY/WIKI/GRAPH.json"
    write_json(overlay / "START_HERE_FOR_ROBOTS.json", entry)
    nested = dict(entry)
    nested["root_resolution"] = "Library root is this file's parent directory's parent; listed paths are library-root-relative."
    write_json(overlay / "ROBOT_READABLE_DIRECTORY/START_HERE.json", nested)
    retrieval = read_json(root / CONFIG)
    retrieval.pop("default_index", None)
    retrieval.update({"default_index_mode": "resolve_from_index_catalog", "index_catalog": CATALOG,
                      "query_policy": QUERY, "current_release_pointer": POINTER,
                      "access_policy": POLICY, "library_state": STATE, "entry_point": "START_HERE_FOR_ROBOTS.json",
                      "doha_index": doha[0], "doha_current_paths_index": doha[1]})
    write_json(overlay / CONFIG, retrieval)
    policy = read_json(root / POLICY)
    policy["content_access"].pop("approved_indexes", None)
    policy["content_access"].update({"approved_indexes_mode": "resolve_from_index_catalog", "doha_approved_indexes": doha})
    write_json(overlay / POLICY, policy)
    write_json(overlay / ROUTER, read_json(root / ROUTER))
    wiki_relative = "ROBOT_READABLE_DIRECTORY/WIKI/GRAPH.json"
    write_json(overlay / wiki_relative, read_json(production_root / wiki_relative))
    evidence_metadata = ("ROBOT_READABLE_DIRECTORY/MANIFESTS/DOCUMENTS_ENRICHED.jsonl",
                         "ROBOT_READABLE_DIRECTORY/CHUNKS/GENERAL_CITATION_SAFE_CHUNKS.jsonl")
    for relative in evidence_metadata:
        (overlay / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(production_root / relative, overlay / relative)
    agents = """# DCSA Library automation policy

Automated consumers must use `START_HERE_FOR_ROBOTS.json` as the canonical entry point and obey `ROBOT_READABLE_DIRECTORY/RETRIEVAL/ROBOT_ACCESS_POLICY.json`.

- Fail closed when entry points, access policy, library state, release pointer, retrieval configuration, index catalog, query policy, or DOHA router are missing or contradictory.
- Automated content access is limited to approved robot-readable paths and indexes.
- Never open, parse, OCR, crawl, chunk, embed, index, or summarize content under `HUMAN_READABLE_DIRECTORY/**`.
- Treat `human_source_path` as citation and human-navigation metadata only.
- Never retrieve content from `OPERATIONS/**`.
- Resolve the active release from `ROBOT_READABLE_DIRECTORY/STATE/CURRENT_CUSTODIAN_RELEASE.json` and require matching published state and approval.
- General retrieval uses that release's indexes listed in `ROBOT_READABLE_DIRECTORY/RETRIEVAL/INDEX_CATALOG.json`, gated by `QUERY_POLICY.json` and each index's `allowed_intents` and `default_allowed` fields.
- DOHA retrieval uses `LOCAL_INDEXES/DOHA_CASE_TOPICS_FTS.sqlite`, requires topic gating or an exact case ID, and must never fall back to the legacy unrestricted DOHA index.
- Do not use an unapproved custodian candidate for production answers.
- Production readiness applies to approved, validated retrieval indexes; unresolved and historical research remain excluded from default answers.
- Do not mutate source content, manifests, catalogs, or indexes without an approved, preview-first maintenance change.
"""
    (overlay / "AGENTS.md").write_text(agents, encoding="utf-8", newline="\n")
    pointer = {
        "schema_version": "1.1", "release_id": release_id, "published_utc": published_utc,
        "approval": approval, "rollback_snapshot": str(rollback_dir), "derived_artifacts_only": not bool(state.get("source_intake_files")),
        "validation": {"valid": True, "publishable": True, "validated_utc": validation["validated_utc"]},
        "metadata_sha256": {relative: sha256_file(overlay / relative) for relative in (STATE, CATALOG, QUERY, POLICY, CONFIG, wiki_relative, *evidence_metadata)},
    }
    write_json(overlay / POINTER, pointer)
    approved_release(overlay, verify_indexes=False)
    sources = {source.relative_to(production_root).as_posix(): source for source in production_root.rglob("*") if source.is_file()}
    sources.update({source.relative_to(overlay).as_posix(): source for source in overlay.rglob("*") if source.is_file()})
    for source in sorted((release_dir / "indexes").glob("*.sqlite")):
        sources[f"LOCAL_INDEXES/CUSTODIAN/{release_id}/{source.name}"] = source
    # Reject path escapes before writing anything. Install the pointer last so a
    # partially completed publication cannot appear to be a coherent new release.
    changed = []
    for relative, source in sources.items():
        target = (root / relative).resolve()
        if not target.is_relative_to(root.resolve()):
            raise ValueError(f"publication path escape: {relative}")
        if not target.is_file() or sha256_file(source) != sha256_file(target):
            changed.append(relative)
    changed.sort(key=lambda relative: (relative == POINTER, relative))
    plan = {"release_id": release_id, "changed_files": changed, "unchanged_files": len(sources) - len(changed),
            "overlay": str(overlay), "rollback_snapshot": str(rollback_dir)}
    write_json(overlay.parent / f"{timestamp}-plan.json", plan)
    if dry_run:
        return {"status": "ready_to_publish", **plan}
    for relative in changed:
        target = root / relative
        if target.exists():
            backup = rollback_dir / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
            snapshots.append(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(target.suffix + ".publishing")
        shutil.copy2(sources[relative], temp)
        os.replace(temp, target)
        copied.append(relative)
    health = approved_release(root, check_integrity=True)
    write_json(overlay.parent / f"{timestamp}-verification.json", {"release_id": release_id, "index_checks": health["index_checks"]})
    write_json(overlay.parent / f"{timestamp}-retrieval-evaluation.json", fresh_evaluation)
    event = reconcile_event(project_root, config, root, release_dir)
    return {"status": "published", "release_id": release_id, "copied": copied, "snapshots": snapshots, "pointer": pointer,
            "production_response_ready": True, "verified_indexes": len(health["index_checks"]), "handoff": event}
