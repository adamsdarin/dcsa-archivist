from __future__ import annotations

import collections
import contextlib
import json
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .audit import audit_library
from .chunks import build_chunks
from .common import HUMAN_PREFIX, ROBOT_PREFIX, iter_jsonl, norm, read_json, sha256_file, sha256_text, utc_now, write_json, write_jsonl
from .decisions import apply_metadata_decisions, load_metadata_decisions
from .enrich import enrich_manifest
from .evals import evaluate_candidate
from .indexes import build_indexes


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


def build_candidate(project_root: Path, root: Path, config: dict[str, Any], release_id: str | None = None, deep: bool = False) -> dict[str, Any]:
    release_id = release_id or release_id_now()
    state_root = project_root / config.get("state_directory", ".custodian")
    release_dir = state_root / "releases" / release_id
    if release_dir.exists():
        raise FileExistsError(f"release already exists: {release_id}")
    release_dir.mkdir(parents=True)

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

    chunks = build_chunks(
        root, records,
        int(config.get("default_chunk_characters", 3200)),
        int(config.get("maximum_chunk_characters", 4800)),
        int(config.get("chunk_overlap_characters", 300)),
    )
    chunks_path = release_dir / "production/ROBOT_READABLE_DIRECTORY/CHUNKS/GENERAL_CITATION_SAFE_CHUNKS.jsonl"
    write_jsonl(chunks_path, chunks)

    indexes_dir = release_dir / "indexes"
    catalog = build_indexes(indexes_dir, records, chunks)
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
    state = {
        "schema_version": "1.0",
        "release_id": release_id,
        "release_status": "candidate_unapproved",
        "generated_utc": utc_now(),
        "library_root_at_build": str(root),
        "production_integrity_healthy": audit["summary"]["integrity_healthy"],
        "production_response_ready": audit["summary"]["production_response_ready"],
        "candidate_response_ready": not publication_blockers,
        "candidate_publishable": not publication_blockers,
        "publication_blockers": publication_blockers,
        "manifest_records": len(records),
        "citation_safe_chunks": len(chunks),
        "answer_eligibility_counts": dict(eligibility),
        "parity": {"relationships": audit["summary"]["manifest_records"], "broken": 0, "human_hash_mode": "deep" if deep else "existence_and_size"},
        "quality_blockers": audit["quality_blockers"],
        "remediation_queue_items": len(remediation_queue),
        "metadata_decisions_applied": metadata_decisions_applied,
        "approved_indexes": [],
        "candidate_indexes": catalog,
        "requires_human_approval": True,
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
            source_cache[robot_rel] = (root / robot_rel).read_text(encoding="utf-8", errors="replace")
        if chunk["content"] not in source_cache[robot_rel]:
            errors.append(f"chunk not found verbatim in robot source: {chunk['chunk_id']}")
        if sha256_text(chunk["content"]) != chunk["content_sha256"]:
            errors.append(f"chunk hash mismatch: {chunk['chunk_id']}")
        if len(errors) > 100:
            break

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
            index_results.append({"path": index_path.name, "integrity": integrity, "chunks": count})
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


def publish_candidate(project_root: Path, root: Path, config: dict[str, Any], release_dir: Path) -> dict[str, Any]:
    validation = validate_candidate(root, release_dir)
    if not validation["valid"]:
        raise RuntimeError("candidate validation failed")
    if not validation["publishable"]:
        raise RuntimeError(f"candidate is not publishable: {validation.get('publication_blockers', [])}")
    approval_path = release_dir / "APPROVAL.json"
    if not approval_path.is_file():
        raise PermissionError("publication requires APPROVAL.json created by the explicit approve command")
    release_id = release_dir.name
    timestamp = release_id_now()
    rollback_dir = project_root / config.get("state_directory", ".custodian") / "rollback" / timestamp
    copied: list[str] = []
    snapshots: list[str] = []

    production_root = release_dir / "production"
    for source in sorted(p for p in production_root.rglob("*") if p.is_file()):
        relative = source.relative_to(production_root)
        target = root / relative
        if target.exists():
            backup = rollback_dir / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
            snapshots.append(relative.as_posix())
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(target.suffix + ".publishing")
        shutil.copy2(source, temp)
        os.replace(temp, target)
        copied.append(relative.as_posix())
    for source in sorted((release_dir / "indexes").glob("*.sqlite")):
        relative = Path("LOCAL_INDEXES/CUSTODIAN") / release_id / source.name
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(relative.as_posix())
    pointer = {
        "schema_version": "1.0", "release_id": release_id, "published_utc": utc_now(),
        "approval": read_json(approval_path), "rollback_snapshot": str(rollback_dir),
        "derived_artifacts_only": True,
    }
    write_json(root / "ROBOT_READABLE_DIRECTORY/STATE/CURRENT_CUSTODIAN_RELEASE.json", pointer)
    return {"status": "published", "release_id": release_id, "copied": copied, "snapshots": snapshots, "pointer": pointer}
