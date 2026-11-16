"""Durable release handoffs. Delivery is a work packet; completion is a receipt."""
from __future__ import annotations

import difflib
import json
import hashlib
import re
from pathlib import Path

from .audit import approved_release_once as approved_release  # the contract's result, once per run for the same bytes
from .common import iter_jsonl, read_json, sha256_file, utc_now, write_json
from .release_contract import bounded_path
from .wiki import build_edges

ENRICHED = "ROBOT_READABLE_DIRECTORY/MANIFESTS/DOCUMENTS_ENRICHED.jsonl"
CHUNKS = "ROBOT_READABLE_DIRECTORY/CHUNKS/GENERAL_CITATION_SAFE_CHUNKS.jsonl"
CONSUMERS = ("dcsa-compare", "fso-guidance-watch")
# A consumer that reviewed the whole source but could not close every citation because
# the library does not hold a cited document says so with this status and the list.
GAPS_STATUS = "completed_with_gaps"
UNHELD_FIELDS = ("title", "cited_at", "needed_for", "handling")
ACQUISITION_DIR = "acquisition-requests"
# Published, hash-bound, per-release change summaries. Consumers use them to tell a
# release that touched nothing an answer depends on from one that did; they carry
# identities and eligibility only, never content.
SUMMARY_DIR = "ROBOT_READABLE_DIRECTORY/STATE/RELEASE_CHANGES"


def compact_summary(changes: dict) -> dict:
    return {
        "schema_version": "1.0", "release_id": changes["release_id"],
        "previous_release_id": changes.get("previous_release_id"), "baseline": bool(changes.get("baseline")),
        "created_utc": changes.get("created_utc"),
        "changes": [{
            "document_id": c["document_id"], "kind": c["kind"], "changed_fields": c.get("changed_fields", []),
            "before_eligibility": (c.get("before") or {}).get("answer_eligibility"),
            "after_eligibility": (c.get("after") or {}).get("answer_eligibility"),
        } for c in changes.get("changes", [])],
    }


def summary_history(library: Path, releases_dir: Path, changes: dict, limit: int = 200) -> dict[str, dict]:
    """Summaries this candidate should publish: its own, plus earlier ones the library lacks.

    Walks previous_release_id through this project's retained release reports and
    stops at the first release the library already summarizes or that has no report.
    """
    output = {changes["release_id"]: compact_summary(changes)}
    previous = changes.get("previous_release_id")
    for _ in range(limit):
        if not previous or (library / SUMMARY_DIR / f"{previous}.json").is_file():
            break
        report = releases_dir / previous / "reports/RELEASE_CHANGES.json"
        if not report.is_file():
            break
        earlier = read_json(report)
        if earlier.get("release_id") != previous:
            break
        output[previous] = compact_summary(earlier)
        previous = earlier.get("previous_release_id")
    return output


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
        if not event["actionable"]:
            continue
        source = Path(event["changes_path"])
        if sha256_file(source) != event["changes_sha256"]:
            raise ValueError("queued change packet changed")
        receipt_path = path.parent / f"{consumer}.receipt.json"
        if verified_receipt(receipt_path, event, consumer):
            continue
        changes = read_json(source)
        result.append({"event": event, "changes": changes,
                       "receipt_issue": "missing_or_unverifiable_receipt" if receipt_path.exists() else "not_acknowledged"})
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


def validate_receipt(receipt, event, consumer):
    if not isinstance(receipt, dict):
        raise ValueError('Receipt must be an object')
    if receipt.get('event_id') != event['event_id'] or receipt.get('consumer') != consumer or receipt.get('changes_sha256') != event['changes_sha256']:
        raise ValueError('receipt does not match the consumer/event/change packet')
    status = receipt.get('status')
    if status not in ('completed', 'no_relevant_change', GAPS_STATUS) or not receipt.get('reviewed_by'):
        raise ValueError('receipt needs reviewed completion or a reasoned no-change disposition')
    gates = ('full_source_review', 'citation_closure', 'coverage_complete')
    unheld = receipt.get('unheld_documents')
    if unheld and status != GAPS_STATUS:
        raise ValueError(f'unheld_documents requires status {GAPS_STATUS}; a receipt may not claim completion while listing documents the library does not hold')
    if status == GAPS_STATUS:
        # The reviewed source cites documents the library does not hold. The consumer read
        # the whole source and says exactly what it could not close; nothing is waved through.
        if receipt.get('full_source_review') is not True:
            raise ValueError('incomplete consumer gate: full_source_review')
        if not isinstance(unheld, list) or not unheld:
            raise ValueError(f'{GAPS_STATUS} requires a non-empty unheld_documents list')
        for item in unheld:
            if not isinstance(item, dict) or any(not isinstance(item.get(key), str) or not item[key].strip() for key in UNHELD_FIELDS):
                raise ValueError(f'each unheld document needs non-empty {", ".join(UNHELD_FIELDS)}')
        if any(not isinstance(receipt.get(key), bool) for key in gates):
            raise ValueError('citation_closure and coverage_complete must each be stated true or false')
        if all(receipt.get(key) is True for key in gates):
            raise ValueError('receipt claims every gate complete while listing unheld_documents')
    else:
        for key in gates:
            if receipt.get(key) is not True:
                raise ValueError(f'incomplete consumer gate: {key}')
    artifacts = receipt.get('artifacts')
    if not receipt.get('summary') or not isinstance(artifacts, list) or not artifacts:
        raise ValueError('receipt requires a summary and hashed review/output artifacts')
    for artifact in artifacts:
        if not isinstance(artifact, dict) or not isinstance(artifact.get('path'), str) or not re.fullmatch(r'[a-f0-9]{64}', str(artifact.get('sha256', ''))):
            raise ValueError('Invalid receipt artifact')


def verified_receipt(path, event, consumer):
    try:
        receipt = read_json(path)
        validate_receipt(receipt, event, consumer)
        if receipt.get('artifact_storage') != 'event_local_v1':
            return False
        for artifact in receipt['artifacts']:
            source = bounded_path(path.parent, artifact['path'], f'{consumer}.artifacts/')
            if sha256_file(source) != artifact['sha256']:
                return False
        return True
    except (OSError, ValueError, TypeError, KeyError):
        return False


def acknowledge(project: Path, config: dict, root: Path, consumer: str, event_id: str, receipt_path: Path) -> dict:
    if consumer not in CONSUMERS:
        raise ValueError("unknown consumer")
    directory = bounded_path(event_directory(project, config, root), event_id, "")
    event = read_json(directory / "event.json")
    if sha256_file(Path(event['changes_path'])) != event['changes_sha256']:
        raise ValueError('queued change packet changed')
    receipt = read_json(receipt_path)
    validate_receipt(receipt, event, consumer)
    retained = []
    for artifact in receipt["artifacts"]:
        path = bounded_path(receipt_path.parent, artifact["path"], "")
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != artifact["sha256"]:
            raise ValueError("consumer artifact hash mismatch")
        retained.append((artifact, payload))
    stored = []
    for artifact, payload in retained:
        relative = f"{consumer}.artifacts/{artifact['sha256']}.bin"
        target = bounded_path(directory, relative, f'{consumer}.artifacts/')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        stored.append({'path': relative, 'sha256': artifact['sha256']})
    target = directory / f"{consumer}.receipt.json"
    recorded = utc_now()
    gaps = receipt["status"] == GAPS_STATUS
    result = {"receipt": str(target), "status": receipt["status"],
              "acknowledgment": "acknowledged_with_gaps" if gaps else "acknowledged"}
    extra = {"acknowledgment": result["acknowledgment"]}
    if gaps:
        # The gap leaves here as a request the Librarian can read, before the receipt is stored.
        request = acquisition_request_path(project, config, event_id, consumer)
        if request.is_file() and read_json(request).get("library_root") != str(root.resolve()):
            raise ValueError(f"an acquisition request for another library already exists: {request}")
        write_json(request, {
            "schema_version": "1.0", "type": "library.acquisition_request", "status": "open",
            "event_id": event_id, "consumer": consumer, "library_root": str(root.resolve()),
            "reviewed_by": receipt["reviewed_by"], "recorded_utc": recorded, "receipt": str(target),
            "note": "Documents a reviewed source cites and the library does not hold. A request does not "
                    "authorize acquisition outside the Librarian's registry and bounds.",
            "requests": [{key: item[key].strip() for key in UNHELD_FIELDS} for item in receipt["unheld_documents"]],
        })
        extra["acquisition_request"] = result["acquisition_request"] = str(request)
        result["unheld_documents"] = len(receipt["unheld_documents"])
    write_json(target, {**receipt, 'artifacts': stored, 'artifact_storage': 'event_local_v1', "recorded_utc": recorded, **extra})
    return result


def acquisition_request_path(project: Path, config: dict, event_id: str, consumer: str) -> Path:
    directory = project / config.get("state_directory", ".custodian") / ACQUISITION_DIR
    return bounded_path(directory, f"{event_id}.{consumer}.json", "")


def acknowledgment_states(project: Path, config: dict, root: Path) -> list[dict]:
    """Every queued event with each consumer's state: pending, acknowledged or acknowledged_with_gaps."""
    output = []
    for path in sorted(event_directory(project, config, root).glob("*/event.json")):
        event = read_json(path)
        row = {"event_id": event["event_id"], "actionable": event["actionable"], "consumers": {}}
        for consumer in CONSUMERS:
            receipt_path = path.parent / f"{consumer}.receipt.json"
            if not event["actionable"]:
                state = {"state": "no_action_required"}
            elif not verified_receipt(receipt_path, event, consumer):
                state = {"state": "pending"}
            else:
                receipt = read_json(receipt_path)
                gaps = receipt["status"] == GAPS_STATUS
                state = {"state": "acknowledged_with_gaps" if gaps else "acknowledged",
                         "status": receipt["status"], "recorded_utc": receipt.get("recorded_utc")}
                if gaps:
                    state["unheld_documents"] = receipt["unheld_documents"]
                    state["acquisition_request"] = receipt.get("acquisition_request")
            row["consumers"][consumer] = state
        output.append(row)
    return output
