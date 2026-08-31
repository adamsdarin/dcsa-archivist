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
    by_identity = {
        (record["source_document_id"], norm(record["robot_text_path"])): record
        for record in records
    }
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
        record = by_identity.get(identity)
        if record is None:
            raise ValueError(f"metadata decision does not match a manifest record: {identity}")
        if record["collection_id"] == "doha_decisions":
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
        if disposition == "verified_current":
            if record["authority_role"] == "unclassified_role":
                raise ValueError(f"cannot activate an unclassified authority role: {identity}")
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
        if decision.get("effective_date"):
            record["effective_date"] = decision["effective_date"]
        record["maintenance_decision"] = decision
        applied += 1
    return applied
