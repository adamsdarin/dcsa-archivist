"""Reviewed renames of existing sources enter isolated builds, never the live corpus.

Publication can add files but used to have no way to move one, so a misnamed source
could only be fixed by editing production directly. A rename plan is staged like
intake: the library is copied, the files move in the copy, and publication installs
the new paths and then retires the old ones, keeping the old bytes in its rollback.
Document IDs never change, so citations by ID keep resolving.
"""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

from .common import iter_jsonl, norm, read_json, utc_now, write_jsonl
from .naming import check_collection_name
from .release_contract import bounded_path
from .staging import stage_tree

PATHS = (("human_source_path", "HUMAN_READABLE_DIRECTORY/"), ("robot_text_path", "ROBOT_READABLE_DIRECTORY/TEXT/"))


def stage_renames(root: Path, destination: Path, plan_path: Path,
                  staging: dict | None = None) -> tuple[list[str], list[dict[str, str]]]:
    """Stage a library root and apply reviewed renames to that staged root.

    Returns the files the release must install and the {from, to} moves publication
    must complete by retiring each old path.
    """
    plan = read_json(plan_path)
    if plan.get("schema_version") != "1.0" or not plan.get("renames"):
        raise ValueError("rename plan requires schema_version 1.0 and nonempty renames")
    entry = read_json(root / "START_HERE_FOR_ROBOTS.json")
    manifest = bounded_path(root, entry["documents"], "ROBOT_READABLE_DIRECTORY/MANIFESTS/")
    relationships = bounded_path(root, entry["relationships"], "ROBOT_READABLE_DIRECTORY/MANIFESTS/")
    records = [r for _, r in iter_jsonl(manifest)]
    pairs = [r for _, r in iter_jsonl(relationships)]
    by_id: dict[str, list[dict]] = {}
    for record in records:
        by_id.setdefault(record["document_id"], []).append(record)
    used = {norm(r[key]).casefold() for r in records for key, _ in PATHS}
    seen: set[str] = set()
    moves: list[dict[str, str]] = []
    now = utc_now()
    for item in plan["renames"]:
        identity = item.get("document_id")
        review = item.get("review", {})
        for field in ("reviewed_by", "reviewed_utc", "reason"):
            if not review.get(field):
                raise ValueError(f"rename requires an attributable review receipt: {field}")
        if identity in seen:
            raise ValueError(f"document renamed twice in one plan: {identity}")
        seen.add(identity)
        matched = by_id.get(identity, [])
        if len(matched) != 1:
            raise ValueError(f"rename must match exactly one manifest record: {identity}")
        record = matched[0]
        if record.get("collection_id") == "doha_decisions":
            raise ValueError("DOHA decision paths are controlled by the dedicated case index")
        history = {"renamed_utc": now, "renamed_by": review["reviewed_by"], "reason": review["reason"]}
        new = {}
        for key, prefix in PATHS:
            old = norm(record[key])
            target = bounded_path(root, item[key], prefix)
            relative = target.relative_to(root.resolve()).as_posix()
            if PurePosixPath(relative).suffix != PurePosixPath(old).suffix:
                raise ValueError(f"a rename may not change the file type: {relative}")
            if not (root / old).is_file():
                raise ValueError(f"source to rename is missing: {old}")
            if sum(norm(r[key]).casefold() == old.casefold() for r in records) != 1:
                # One compiled source can back many records; moving it would strand the others.
                raise ValueError(f"path is shared by other records: {old}")
            if relative.casefold() == old.casefold():
                # Windows resolves both spellings to one file; a case-only change needs its own tooling.
                raise ValueError(f"rename does not change the path: {relative}")
            if target.exists() or relative.casefold() in used:
                raise ValueError(f"rename may not overwrite a source: {relative}")
            used.add(relative.casefold())
            history[f"previous_{key}"] = old
            new[key] = relative
            moves.append({"from": old, "to": relative})
        title = item.get("title")
        if title is not None:
            if not isinstance(title, str) or not title.strip():
                raise ValueError(f"rename title must be non-empty text: {identity}")
            history["previous_title"] = record.get("title")
            record["title"] = title.strip()
        record.update(new)
        check_collection_name(record)
        record.setdefault("rename_history", []).append(history)
        for pair in pairs:
            if pair.get("document_id") == identity:
                pair.update(new)
                if "human_readable_path" in pair:
                    pair["human_readable_path"] = new["human_source_path"]
    # No production writes or partial staging before every item passes. Unchanged files
    # are hard links (staging.py); the two manifests rewritten below are real copies. A
    # move renames the staged link, which leaves the library's own name and bytes alone.
    changed = [manifest.relative_to(root).as_posix(), relationships.relative_to(root).as_posix()]
    record_of_staging = stage_tree(root, destination, copy=changed)
    if staging is not None:
        staging.update(record_of_staging)
    for move in moves:
        target = destination / move["to"]
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(destination / move["from"], target)
    write_jsonl(destination / changed[0], records)
    write_jsonl(destination / changed[1], pairs)
    return changed + [move["to"] for move in moves], moves
