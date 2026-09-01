from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import norm, read_json


ALLOWED_DECISIONS = {"verified_current", "superseded", "historical", "exclude"}


def load_metadata_decisions(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    payload = read_json(path)
    if payload.get("schema_version") != "1.0" or not isinstance(payload.get("decisions"), list):
        raise ValueError(f"invalid metadata decisions file: {path}")
    return payload["decisions"]


def apply_metadata_decisions(records: list[dict[str, Any]], decisions: list[dict[str, Any]]) -> int:
    by_identity: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in records:
        identity = (record["source_document_id"], norm(record["robot_text_path"]))
        by_identity.setdefault(identity, []).append(record)
    seen: set[tuple[str, str]] = set()
    applied = 0
    for decision in decisions:
        required = {"source_document_id", "robot_text_path", "decision", "verified_utc", "verified_by", "evidence", "note"}
        missing = sorted(required - decision.keys())
        if missing:
            raise ValueError(f"metadata decision missing fields {missing}")
        identity = (str(decision["source_document_id"]), norm(decision["robot_text_path"]))
        if identity in seen:
            raise ValueError(f"duplicate metadata decision: {identity}")
        seen.add(identity)
        matched_records = by_identity.get(identity)
        if not matched_records:
            raise ValueError(f"metadata decision does not match a manifest record: {identity}")
        if any(record["collection_id"] == "doha_decisions" for record in matched_records):
            raise ValueError("DOHA lifecycle is controlled by the dedicated case index, not metadata decisions")
        disposition = decision["decision"]
        if disposition not in ALLOWED_DECISIONS:
            raise ValueError(f"unsupported metadata decision: {disposition}")
        evidence = decision["evidence"]
        if disposition in {"verified_current", "superseded", "historical"}:
            if not isinstance(evidence, list) or not evidence:
                raise ValueError(f"{disposition} requires official-source evidence: {identity}")
            for item in evidence:
                if not isinstance(item, dict) or not str(item.get("url", "")).startswith("https://"):
                    raise ValueError(f"evidence requires an HTTPS official-source URL: {identity}")
        if disposition == "verified_current" and any(record["authority_role"] == "unclassified_role" for record in matched_records):
            raise ValueError(f"cannot activate an unclassified authority role: {identity}")
        # A manifest identity can resolve to more than one legacy record (e.g. two
        # print sizes of the same poster sharing one document_id and robot_text_path).
        # Every matching record must be mutated together, or a decision applied to
        # only one arbitrary survivor leaves its sibling's currency stale. Content-hash
        # duplicate exclusion (enrich_manifest, run before this) already picked the
        # canonical record among them; no disposition may re-open a non-canonical
        # copy as independently answer-eligible or historical-eligible.
        for record in matched_records:
            if disposition == "verified_current":
                record["current_status"] = "current"
                record["answer_eligibility"] = "answer_eligible"
                record["answer_eligibility_basis"] = "official_source_review_verified_current"
            elif disposition in {"superseded", "historical"}:
                record["current_status"] = disposition
                record["answer_eligibility"] = "historical_only"
                record["answer_eligibility_basis"] = f"official_source_review_{disposition}"
            else:
                record["answer_eligibility"] = "excluded_by_review"
                record["answer_eligibility_basis"] = "approved_maintenance_exclusion"
            if record.get("duplicate_of"):
                record["answer_eligibility"] = "excluded_duplicate"
                record["answer_eligibility_basis"] = "identical_robot_content_sha256"
            if decision.get("effective_date"):
                record["effective_date"] = decision["effective_date"]
            record["maintenance_decision"] = decision
        applied += 1
    return applied
