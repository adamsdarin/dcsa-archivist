"""Reviewed quarantine packages enter isolated builds, never the live corpus."""
from __future__ import annotations

import shutil
from pathlib import Path
from urllib.parse import urlparse

from .common import iter_jsonl, read_json, sha256_file, write_jsonl
from .release_contract import bounded_path


def stage_intake(root: Path, destination: Path, plan_path: Path) -> list[str]:
    """Copy a library and apply hash-bound, reviewed additions to that copy.

    The agent supplies taxonomy/identity/lifecycle and a checked robot extraction.
    This function does not pretend a PDF extractor can establish those facts.
    New editions require new IDs and paths; metadata decisions handle supersession.
    """
    plan = read_json(plan_path)
    if plan.get("schema_version") != "1.0" or not plan.get("items"):
        raise ValueError("intake plan requires schema_version 1.0 and nonempty items")
    entry = read_json(root / "START_HERE_FOR_ROBOTS.json")
    manifest = bounded_path(root, entry["documents"], "ROBOT_READABLE_DIRECTORY/MANIFESTS/")
    relationships = bounded_path(root, entry["relationships"], "ROBOT_READABLE_DIRECTORY/MANIFESTS/")
    records = [r for _, r in iter_jsonl(manifest)]
    pairs = [r for _, r in iter_jsonl(relationships)]
    ids = {r["document_id"] for r in records}
    used = {str(r[k]).replace("\\", "/").casefold() for r in records for k in ("human_source_path", "robot_text_path")}
    additions = []
    for item in plan["items"]:
        package_path = bounded_path(plan_path.parent, item["package"], "")
        package = read_json(package_path)
        source = bounded_path(package_path.parent, package["source_filename"], "")
        robot = bounded_path(plan_path.parent, item["robot_file"], "")
        record = dict(item["record"])
        review = item.get("review", {})
        if not review.get("reviewed_by") or not review.get("reviewed_utc"):
            raise ValueError("intake requires an attributable review receipt")
        for check in ("identity", "provenance", "extraction", "parity", "taxonomy", "lifecycle"):
            if not review.get(check):
                raise ValueError(f"missing intake review evidence: {check}")
        if package.get("approval_state") != "quarantined_unreviewed":
            raise ValueError("expected quarantined Librarian package")
        for field in ("requested_source_uri", "resolved_source_uri"):
            if urlparse(package.get(field, "")).scheme != "https":
                raise ValueError(f"missing HTTPS provenance: {field}")
        if not package.get("retrieved_at") or not package.get("mime_type"):
            raise ValueError("missing retrieval provenance")
        if sha256_file(source) != package["source_sha256"] or source.stat().st_size != package["source_bytes"]:
            raise ValueError("quarantined source hash/size mismatch")
        if sha256_file(robot) != item["robot_sha256"] or not robot.read_text(encoding="utf-8").strip():
            raise ValueError("robot extraction hash mismatch or empty text")
        for key in ("document_id", "collection_id", "domain", "authority_tier", "current_status"):
            if record.get(key) in (None, ""):
                raise ValueError(f"missing reviewed record field: {key}")
        if record["document_id"] in ids:
            raise ValueError("new editions require a unique document ID")
        ids.add(record["document_id"])
        for key, prefix in (("human_source_path", "HUMAN_READABLE_DIRECTORY/"), ("robot_text_path", "ROBOT_READABLE_DIRECTORY/TEXT/")):
            path = bounded_path(root, record[key], prefix)
            relative = path.relative_to(root.resolve()).as_posix()
            if path.exists() or relative.casefold() in used:
                raise ValueError("intake may not overwrite a source; use a new edition path")
            record[key] = relative
            used.add(relative.casefold())
        record.update(canonical_source_uri=package["resolved_source_uri"],
                      canonical_source_url=package["resolved_source_uri"],
                      source_sha256=package["source_sha256"], robot_sha256=item["robot_sha256"],
                      retrieved_utc=package["retrieved_at"], mime_type=package["mime_type"],
                      intake_review=review, intake_provenance=package)
        additions.append((record, source, robot))
    # No production writes or partial staging before every item passes.
    # A full copy is deliberate: existing audit/index contracts see a coherent root.
    # Exclude operational history; never use hard links for mutable manifests.
    shutil.copytree(root, destination, ignore=shutil.ignore_patterns(".custodian", "OPERATIONS", ".git"))
    changed = [manifest.relative_to(root).as_posix(), relationships.relative_to(root).as_posix()]
    for record, source, robot in additions:
        for key, artifact in (("human_source_path", source), ("robot_text_path", robot)):
            target = destination / record[key]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(artifact, target)
            changed.append(record[key])
        records.append(record)
        pairs.append({"document_id": record["document_id"], "human_source_path": record["human_source_path"],
                      "robot_text_path": record["robot_text_path"], "relation": "machine_readable_representation_of"})
    write_jsonl(destination / changed[0], records)
    write_jsonl(destination / changed[1], pairs)
    return changed
