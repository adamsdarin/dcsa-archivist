"""Durable release handoffs. Delivery is a work packet; completion is a receipt."""
from __future__ import annotations

import difflib
import json
from pathlib import Path

from .common import iter_jsonl, read_json, sha256_file, utc_now, write_json
from .release_contract import approved_release, bounded_path
from .wiki import build_edges

ENRICHED = "ROBOT_READABLE_DIRECTORY/MANIFESTS/DOCUMENTS_ENRICHED.jsonl"
CHUNKS = "ROBOT_READABLE_DIRECTORY/CHUNKS/GENERAL_CITATION_SAFE_CHUNKS.jsonl"
CONSUMERS = ("dcsa-compare", "fso-guidance-watch")


def _rows(path: Path) -> list[dict]:
    return [r for _, r in iter_jsonl(path)] if path.is_file() else []


def build_changes(root: Path, records: list[dict], chunks: list[dict], release_id: str) -> dict:
    previous_id = None
    previous = []
    old_chunks = []
    if (root / "ROBOT_READABLE_DIRECTORY/STATE/CURRENT_CUSTODIAN_RELEASE.json").is_file():
        health = approved_release(root)
        previous_id = health["release_id"]
        previous = _rows(root / ENRICHED)
        old_chunks = _rows(root / CHUNKS)
        if not previous or not old_chunks:
            raise ValueError("approved baseline lacks comparison manifests/chunks")
    old = {r["document_id"]: r for r in previous}
    new = {r["document_id"]: r for r in records}
    fields = ("robot_content_sha256", "current_status", "authority_role", "answer_eligibility", "authority_tier", "title", "effective_date",
              "human_source_path", "robot_text_path", "collection_id", "canonical_source_uri", "canonical_source_url")
    changes = []
    for identity in sorted(old.keys() | new.keys()):
        before, after = old.get(identity), new.get(identity)
        differing = [f for f in fields if (before or {}).get(f) != (after or {}).get(f)]
        if before is not None and after is not None and not differing:
            continue
        changes.append({"document_id": identity, "kind": "added" if before is None else "removed" if after is None else "changed",
                        "changed_fields": differing, "before": before, "after": after})
    touched = {c["document_id"] for c in changes}
    pairs = [e for e in build_edges(records) if e["edge_type"] == "supersedes" and
             (e["from_document_id"] in touched or e["to_document_id"] in touched)]
    # Candidate relationships are leads, never proof of supersession.
    selected = touched | {e[k] for e in pairs for k in ("from_document_id", "to_document_id")}
    return {"schema_version": "1.0", "release_id": release_id, "previous_release_id": previous_id, "created_utc": utc_now(),
            "baseline": previous_id is None, "changes": changes, "comparison_leads": pairs,
            "before_chunks": [c for c in old_chunks if c["document_id"] in selected],
            "after_chunks": [c for c in chunks if c["document_id"] in selected],
            "interpretation_status": "pending_full_source_review"}


def event_directory(project: Path, config: dict, root: Path) -> Path:
    # Separate queues for different configured libraries, even with the same release ID.
    import hashlib
    key = hashlib.sha256(str(root.resolve()).casefold().encode()).hexdigest()[:16]
    return project / config.get("state_directory", ".custodian") / "events" / key


def reconcile_event(project: Path, config: dict, root: Path, release: Path) -> dict:
    health = approved_release(root, check_integrity=True)
    identity = health["release_id"]
    if release.name != identity:
        raise ValueError("only the current verified release may emit a handoff")
    changes = read_json(release / "reports/RELEASE_CHANGES.json")
    if changes["release_id"] != identity:
        raise ValueError("change packet release mismatch")
    manifest = read_json(release / "RELEASE_MANIFEST.json")
    expected = next(x["sha256"] for x in manifest["files"] if x["path"] == "reports/RELEASE_CHANGES.json")
    if sha256_file(release / "reports/RELEASE_CHANGES.json") != expected:
        raise ValueError("change packet hash mismatch")
    target = event_directory(project, config, root) / identity / "event.json"
    event = {"schema_version": "1.0", "event_id": identity, "type": "library.release.published",
             "library_root": str(root.resolve()), "changes_sha256": expected,
             "changes_path": str((release / "reports/RELEASE_CHANGES.json").resolve()),
             "consumers": list(CONSUMERS), "actionable": bool(changes["changes"])}
    if target.is_file():
        if read_json(target) != event:
            raise ValueError("conflicting event for an existing release ID")
    else:
        write_json(target, event)
    return {"event": str(target), "actionable": event["actionable"]}


def pending_events(project: Path, config: dict, root: Path, consumer: str) -> list[dict]:
    if consumer not in CONSUMERS:
        raise ValueError("unknown release consumer")
    approved_release(root)
    result = []
    for path in sorted(event_directory(project, config, root).glob("*/event.json")):
        event = read_json(path)
        if not event["actionable"] or (path.parent / f"{consumer}.receipt.json").exists():
            continue
        source = Path(event["changes_path"])
        if sha256_file(source) != event["changes_sha256"]:
            raise ValueError("queued change packet changed")
        changes = read_json(source)
        result.append({"event": event, "changes": changes})
    return sorted(result, key=lambda packet: packet["changes"].get("created_utc", ""))


def comparison_report(changes: dict) -> dict:
    """Exact chunk deltas for review; no inferred legal conclusions."""
    def content(side, identity):
        return "\n".join(c["content"] for c in changes[side] if c["document_id"] == identity).splitlines()
    pairs = [(c["document_id"], c["document_id"], "same_document_id") for c in changes["changes"]]
    pairs += [(e["to_document_id"], e["from_document_id"], "unverified_issuance_family_lead") for e in changes["comparison_leads"]]
    diffs = []
    for before, after, basis in pairs:
        left = content("before_chunks", before) or content("after_chunks", before)
        right = content("after_chunks", after)
        diffs.append({"before_document_id": before, "after_document_id": after, "basis": basis,
                      "diff": "\n".join(difflib.unified_diff(left, right, fromfile=before, tofile=after, lineterm=""))})
    return {"release_id": changes["release_id"], "status": "evidence_prepared_interpretation_pending",
            "supersession_verified": False, "limitations": "Chunk deltas are navigation aids. Read full approved robot sources and close citations before findings.", "comparisons": diffs}


def acknowledge(project: Path, config: dict, root: Path, consumer: str, event_id: str, receipt_path: Path) -> dict:
    if consumer not in CONSUMERS:
        raise ValueError("unknown consumer")
    directory = bounded_path(event_directory(project, config, root), event_id, "")
    event = read_json(directory / "event.json")
    receipt = read_json(receipt_path)
    if receipt.get("event_id") != event_id or receipt.get("consumer") != consumer or receipt.get("changes_sha256") != event["changes_sha256"]:
        raise ValueError("receipt does not match the consumer/event/change packet")
    if receipt.get("status") not in ("completed", "no_relevant_change") or not receipt.get("reviewed_by"):
        raise ValueError("receipt needs reviewed completion or a reasoned no-change disposition")
    for key in ("full_source_review", "citation_closure", "coverage_complete"):
        if receipt.get(key) is not True:
            raise ValueError(f"incomplete consumer gate: {key}")
    if not receipt.get("summary") or not receipt.get("artifacts"):
        raise ValueError("receipt requires a summary and hashed review/output artifacts")
    for artifact in receipt["artifacts"]:
        path = bounded_path(receipt_path.parent, artifact["path"], "")
        if sha256_file(path) != artifact["sha256"]:
            raise ValueError("consumer artifact hash mismatch")
    target = directory / f"{consumer}.receipt.json"
    write_json(target, {**receipt, "recorded_utc": utc_now()})
    return {"receipt": str(target), "status": receipt["status"]}
