from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import norm, read_json


ALLOWED_DECISIONS = {"verified_current", "superseded", "historical", "exclude", "provenance"}


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
        if disposition == "provenance":
            # Records where an official URL came from: only an exact byte match between
            # the reacquired file and the retained one. It changes no lifecycle state.
            _apply_provenance(decision, matched_records, identity)
            applied += 1
            continue
        if disposition in {"verified_current", "superseded", "historical"}:
            if not isinstance(evidence, list) or not evidence:
                raise ValueError(f"{disposition} requires official-source evidence: {identity}")
            for item in evidence:
                if not isinstance(item, dict) or not str(item.get("url", "")).startswith("https://"):
                    raise ValueError(f"evidence requires an HTTPS official-source URL: {identity}")
        if disposition == "verified_current" and any(record["authority_role"] == "unclassified_role" for record in matched_records):
            raise ValueError(f"cannot activate an unclassified authority role: {identity}")
        title = decision.get("title")
        if title is not None:
            # A reviewed display title. Paths, IDs and source bytes are untouched, so
            # consumer citations keep resolving; the manifest's own title is kept.
            if not isinstance(title, str) or not title.strip():
                raise ValueError(f"title override must be non-empty text: {identity}")
            if not isinstance(evidence, list) or not evidence:
                raise ValueError(f"title override requires official-source evidence: {identity}")
        if decision.get("canonical"):
            _promote_canonical(records, matched_records, identity)
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
            if title is not None:
                record.setdefault("source_title", record.get("title"))
                record["title"] = title.strip()
                record["title_basis"] = "official_source_review"
            record["maintenance_decision"] = decision
        applied += 1
    return applied


def _promote_canonical(records: list[dict[str, Any]], matched: list[dict[str, Any]], identity: tuple[str, str]) -> None:
    """Make a reviewed record the canonical copy of its content-duplicate group.

    enrich_manifest picks the canonical copy by authority role and path shape,
    which cannot see a lifecycle review: a mislabelled copy filed under a higher
    authority folder wins over the correctly named one. A reviewed decision states
    the choice once, durably, instead of hand edits that the next enrich resets.
    """
    if len(matched) != 1:
        raise ValueError(f"canonical decision must match exactly one record: {identity}")
    chosen = matched[0]
    group_id = chosen["canonical_document_id"]
    group = [record for record in records if record["canonical_document_id"] == group_id]
    if len(group) < 2:
        raise ValueError(f"canonical decision has no duplicate group: {identity}")
    new_id = chosen["document_id"]
    for record in group:
        record["canonical_document_id"] = new_id
        if record is chosen:
            record["duplicate_of"] = None
        else:
            record["duplicate_of"] = new_id
            record["answer_eligibility"] = "excluded_duplicate"
            record["answer_eligibility_basis"] = "reviewed_canonical_choice"


def _apply_provenance(decision: dict[str, Any], matched: list[dict[str, Any]], identity: tuple[str, str]) -> None:
    url, digest = decision.get("source_url"), decision.get("source_sha256")
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError(f"provenance requires an HTTPS source_url: {identity}")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError(f"provenance requires the reacquired source_sha256: {identity}")
    for record in matched:
        retained = record.get("human_artifact_sha256")
        if retained is None:
            raise ValueError(f"provenance needs a deep audit hash of the retained file: {identity}")
        if retained != digest:
            raise ValueError(f"provenance bytes differ from the retained file: {identity}")
        record["source_url"] = url
        record["source_url_basis"] = "reacquired_bytes_identical"
        record["source_url_verified_utc"] = decision["verified_utc"]


def provenance_decisions(ledger_rows: list[dict[str, Any]], records_by_id: dict[str, dict[str, Any]],
                         existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Turn the Librarian's verified provenance ledger into reviewed decisions.

    Only `verified` rows qualify; bytes_differ rows stay for human review. A record
    that already has a decision of any kind is left alone so reviewed lifecycle
    choices are never overwritten.
    """
    decided = {(str(d["source_document_id"]), norm(d["robot_text_path"])) for d in existing}
    output: list[dict[str, Any]] = []
    for row in ledger_rows:
        record = records_by_id.get(row.get("document_id"))
        if row.get("status") != "verified" or record is None:
            continue
        identity = (str(record["document_id"]), norm(record["robot_text_path"]))
        if identity in decided:
            continue
        decided.add(identity)
        url = row.get("resolved_url") or row["requested_url"]
        output.append({
            "source_document_id": identity[0], "robot_text_path": record["robot_text_path"],
            "decision": "provenance", "source_url": url, "source_sha256": row["source_sha256"],
            "verified_utc": row["checked_utc"], "verified_by": f"Librarian byte match, run {row.get('run_id', 'unknown')}",
            "evidence": [{"url": url, "observation": f"Reacquired bytes sha256 {row['source_sha256']} equal the retained file."}],
            "note": "Provenance only; lifecycle and currency are unchanged and still need their own review.",
        })
    return output
