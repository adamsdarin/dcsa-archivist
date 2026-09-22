"""Carry reviewed DOHA eras and source provenance into every store a consumer reads.

The era of a decision appears in six places: the two DOHA path manifests, the
path index, the topic index (``decisions`` and ``corpus``), and the DOHA rows of
the source manifest. A consumer filtering on any one of them must get the same
answer, so a candidate rewrites all of them from one classification and
validation refuses a candidate where any copy disagrees or where an era no
longer follows the decision date.

Paths and folders are untouched: the ``PRE_SEAD_4``/``POST_SEAD_4`` folder in a
path is a storage location from an earlier import, not an era, and moving
files would break every citation that names them.
"""
from __future__ import annotations

import collections
import contextlib
import json
import shutil
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

from .common import iter_jsonl, read_json, utc_now, write_json, write_jsonl
from .doha_era import ERA_RULE, ERAS, SEAD4_EFFECTIVE, classify, era_for

ERA_MANIFEST = "ROBOT_READABLE_DIRECTORY/MANIFESTS/DOHA_SEAD4_ERA.jsonl"
PATH_MANIFEST = "ROBOT_READABLE_DIRECTORY/MANIFESTS/DOHA_CURRENT_PATHS.jsonl"
RULES = "ROBOT_READABLE_DIRECTORY/MANIFESTS/DOHA_SEAD4_RETRIEVAL_RULES.json"
ROUTER = "ROBOT_READABLE_DIRECTORY/MANIFESTS/DOHA_SEAD4_SEARCH_ROUTER.json"
DOCUMENTS = "ROBOT_READABLE_DIRECTORY/MANIFESTS/documents.jsonl"
CONTENT = "LOCAL_INDEXES/DOHA_CASE_TOPICS_FTS.sqlite"
PATHS = "LOCAL_INDEXES/DOHA_CURRENT_PATHS.sqlite"
RULE_ID = "decision_date_on_or_after_2017-06-08"
PRIORITY = {"post_sead4": 100, "pre_sead4": 25, "undetermined": 10}
PROVENANCE_FIELDS = ("source_url", "source_url_basis", "source_listing_page", "source_listing_title",
                     "source_listing_captured_utc", "source_url_alternates")
PROVENANCE_BASES = ("official_listing_label", "legacy_download_bytes_identical")


def load_reviews(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    payload = read_json(path)
    if payload.get("schema_version") != "1.0" or not isinstance(payload.get("reviews"), list):
        raise ValueError(f"invalid DOHA era reviews file: {path}")
    reviews = {}
    for review in payload["reviews"]:
        identity = review.get("document_id")
        if not identity or identity in reviews:
            raise ValueError(f"DOHA era review needs a unique document_id: {identity}")
        reviews[identity] = review
    return reviews


def load_provenance(path: Path) -> dict[str, dict[str, Any]]:
    """Recorded official URLs by document. Only a URL an official listing or a byte match names is kept."""
    if not path.is_file():
        return {}
    output = {}
    for _, row in iter_jsonl(path):
        url = row.get("source_url")
        if not isinstance(url, str) or not url.startswith("https://doha.ogc.osd.mil/"):
            raise ValueError(f"DOHA provenance requires an official HTTPS DOHA URL: {row.get('document_id')}")
        if row.get("source_url_basis") not in PROVENANCE_BASES:
            raise ValueError(f"unsupported DOHA provenance basis: {row.get('document_id')}")
        if row["document_id"] in output:
            raise ValueError(f"duplicate DOHA provenance row: {row['document_id']}")
        output[row["document_id"]] = row
    return output


def _resolve(production: Path, root: Path, relative: str) -> Path:
    staged = production / relative
    return staged if staged.is_file() else root / relative


def _read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def classify_rows(root: Path, reviews: dict[str, dict[str, Any]], provenance: dict[str, dict[str, Any]],
                  overlay: Path | None = None) -> list[dict[str, Any]]:
    """Every DOHA path row with its era, date, basis and recorded source URL.

    ``overlay`` is a candidate's production tree; its files take precedence over the library's.
    """
    here = (lambda relative: _resolve(overlay, root, relative)) if overlay else (lambda relative: root / relative)
    with contextlib.closing(_read_only(here(CONTENT))) as db:
        case_ids = dict(db.execute("SELECT document_id,case_id FROM decisions"))
        rows = []
        for _, row in iter_jsonl(here(PATH_MANIFEST)):
            identity = row["document_id"]
            robot = here(row["robot_text_path"])
            if robot.is_file():
                text, evidence = robot.read_text(encoding="utf-8", errors="replace"), "robot_text"
            else:
                # The indexed copy is the exact text the DOHA stores already serve.
                found = db.execute("SELECT content FROM corpus WHERE document_id=?", (identity,)).fetchone()
                text, evidence = (found[0] if found else ""), "doha_index_copy_robot_file_missing"
            source = provenance.get(identity, {})
            case_id = case_ids.get(identity) or row["case_stem"].split(".")[0]
            result = classify(text, case_id, reviews.get(identity), source.get("source_listing_title"))
            era = result["sead4_era"]
            updated = dict(row)
            updated.update(current_group=ERAS[era], sead4_era=era, retrieval_priority=PRIORITY[era],
                           decision_date=result["decision_date"], decision_date_basis=result["decision_date_basis"],
                           era_basis=result["era_basis"], era_rule=RULE_ID, date_conflicts=result["date_conflicts"],
                           era_evidence_text=evidence)
            updated.update({field: source.get(field) for field in PROVENANCE_FIELDS})
            updated["source_url_alternates"] = updated["source_url_alternates"] or []
            rows.append(updated)
    return rows


def build(root: Path, production: Path, reviews: dict[str, dict[str, Any]],
          provenance: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Write corrected DOHA stores into the candidate. The live library is only read."""
    rows = classify_rows(root, reviews, provenance)
    by_id = {row["document_id"]: row for row in rows}
    before = {row["document_id"]: row for _, row in iter_jsonl(root / PATH_MANIFEST)}
    for relative in (ERA_MANIFEST, PATH_MANIFEST):
        write_jsonl(production / relative, rows)
    counts = collections.Counter(row["sead4_era"] for row in rows)
    corrections = collections.Counter(f"{before[i].get('sead4_era')}->{r['sead4_era']}" for i, r in by_id.items()
                                      if before[i].get("sead4_era") != r["sead4_era"])
    rules = read_json(root / RULES) if (root / RULES).is_file() else {}
    superseded = {key: rules[key] for key in ("cutoff", "delineation_case", "delineation_case_status") if key in rules}
    if rules.get("rule_id") == RULE_ID:
        superseded = rules.get("superseded_rule") or {}
    write_json(production / RULES, {
        "schema_version": "2.0",
        "rule_id": RULE_ID,
        "rule": ERA_RULE,
        "cutoff": SEAD4_EFFECTIVE.isoformat(),
        "cutoff_basis": "SEAD 4 effective date; DOHA applied it to decisions issued on or after that date",
        "date_source": "the decision's own stated date (DATE: header, or the caption date line above 'Decision'), "
                       "checked against its docket year, recorded procedural events and, when provenance records it, "
                       "the year of the official DOHA listing page",
        "never_used": ["case number order", "file or folder name", "the PRE_SEAD_4/POST_SEAD_4 folder in a path"],
        "folder_note": "The PRE_SEAD_4 and POST_SEAD_4 folders in human_source_path and robot_text_path are storage "
                       "locations from an earlier import. Read current_group or sead4_era, never the folder.",
        "groups": {"POST_SEAD_4": "Primary current-policy precedent; default search scope for drafting.",
                   "PRE_SEAD_4": "Historical context; rank after post-SEAD 4 decisions.",
                   "UNDETERMINED": "Issue date not established; excluded from default retrieval until reviewed."},
        "retrieval_priority": {ERAS[era]: value for era, value in PRIORITY.items()},
        "default_search_order": ["post-SEAD 4 decisions", "pre-SEAD 4 historical context"],
        "writing_guardrail": rules.get("writing_guardrail", "For current-policy writing, search and cite post-SEAD 4 "
                                       "decisions first. Use pre-SEAD 4 decisions for historical context only."),
        "era_counts": {ERAS[era]: counts.get(era, 0) for era in PRIORITY},
        "superseded_rule": superseded or None,
    })
    router = read_json(root / ROUTER) if (root / ROUTER).is_file() else {}
    router.update(era_manifest=ERA_MANIFEST, era_rules=RULES, era_rule=ERA_RULE,
                  source_url_field="source_url; null when no official URL is recorded. Never derive one from a case number.")
    write_json(production / ROUTER, router)
    changed_documents = _patch_documents(root, production, by_id)
    changed_paths = _patch_index(root, production, PATHS, "current_paths", ("current_group", "authority_priority"), by_id)
    changed_content = _patch_index(root, production, CONTENT, "decisions", ("current_group", "retrieval_priority"), by_id,
                                   fts_table="corpus")
    return {"schema_version": "1.0", "generated_utc": utc_now(), "rule_id": RULE_ID, "decisions": len(rows),
            "era_counts": dict(counts), "corrections": dict(corrections),
            "date_conflicts": sum(bool(row["date_conflicts"]) for row in rows),
            "robot_text_missing": sum(row["era_evidence_text"] != "robot_text" for row in rows),
            "source_urls_recorded": sum(bool(row["source_url"]) for row in rows),
            "source_url_basis": dict(collections.Counter(row["source_url_basis"] for row in rows if row["source_url"])),
            "rewritten": {"documents_rows": changed_documents, "path_index_rows": changed_paths,
                          "topic_index_rows": changed_content},
            "undetermined": [{"document_id": row["document_id"], "case_stem": row["case_stem"], "era_basis": row["era_basis"],
                              "date_conflicts": row["date_conflicts"]} for row in rows if row["sead4_era"] == "undetermined"]}


def _patch_documents(root: Path, production: Path, by_id: dict[str, dict[str, Any]]) -> int:
    """Rewrite only the DOHA lines whose era changed; every other line stays byte-identical."""
    lines = (root / DOCUMENTS).read_text(encoding="utf-8").splitlines(keepends=True)
    changed = 0
    for number, line in enumerate(lines):
        if '"doha_decisions"' not in line:
            continue
        record = json.loads(line)
        row = by_id.get(record.get("document_id"))
        if row is None or record.get("collection_id") != "doha_decisions":
            continue
        wanted = {"current_group": row["current_group"], "doha_group": row["current_group"],
                  "retrieval_priority": row["retrieval_priority"], "authority_priority": row["retrieval_priority"]}
        if all(record.get(key) == value for key, value in wanted.items()):
            continue
        record.update(wanted)
        lines[number] = json.dumps(record, ensure_ascii=False) + ("\n" if line.endswith("\n") else "")
        changed += 1
    if changed:
        target = production / DOCUMENTS
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("".join(lines), encoding="utf-8", newline="")
    return changed


def _patch_index(root: Path, production: Path, relative: str, table: str, columns: tuple[str, str],
                 by_id: dict[str, dict[str, Any]], fts_table: str | None = None) -> int:
    """Copy an index into the candidate and correct its era columns; leave it out when nothing differs."""
    group_column, priority_column = columns
    with contextlib.closing(_read_only(root / relative)) as db:
        stale = [(row["current_group"], row["retrieval_priority"], identity)
                 for identity, group, priority in db.execute(f"SELECT document_id,{group_column},{priority_column} FROM {table}")
                 if (row := by_id.get(identity)) and (group, priority) != (row["current_group"], row["retrieval_priority"])]
    if not stale:
        return 0
    target = production / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / relative, target)
    with contextlib.closing(sqlite3.connect(target)) as db, db:
        db.executemany(f"UPDATE {table} SET {group_column}=?,{priority_column}=? WHERE document_id=?", stale)
        if fts_table:
            db.executemany(f"UPDATE {fts_table} SET current_group=? WHERE document_id=?",
                           [(group, identity) for group, _, identity in stale])
    return len(stale)


def apply_to_records(records: list[dict[str, Any]], production: Path, root: Path) -> int:
    """Carry the candidate's eras into enriched records, which enrich read from the live index."""
    by_id = {row["document_id"]: row for _, row in iter_jsonl(_resolve(production, root, ERA_MANIFEST))}
    applied = 0
    for record in records:
        row = by_id.get(record.get("document_id"))
        if row is None or record.get("collection_id") != "doha_decisions":
            continue
        for key in ("current_group", "doha_group"):
            if key in record:
                record[key] = row["current_group"]
        if "retrieval_priority" in record:
            record["retrieval_priority"] = row["retrieval_priority"]
        metadata = record.get("doha_case_metadata")
        if isinstance(metadata, dict):
            metadata.update(current_group=row["current_group"], sead4_era=row["sead4_era"],
                            decision_date=row["decision_date"])
        applied += 1
    return applied


def check(production: Path, root: Path, reviews: dict[str, dict[str, Any]] | None = None,
          provenance: dict[str, dict[str, Any]] | None = None, recompute: bool = True,
          enriched: Path | None = None) -> list[str]:
    """Errors when any DOHA store disagrees, or an era does not follow the decision-date rule.

    ``recompute`` reclassifies every decision from its text, which is what stops a
    case-number or folder rule from returning under a new name.
    """
    errors: list[str] = []
    rules_path = _resolve(production, root, RULES)
    rules = read_json(rules_path) if rules_path.is_file() else {}
    if rules.get("rule_id") != RULE_ID or rules.get("cutoff") != SEAD4_EFFECTIVE.isoformat():
        errors.append(f"DOHA era rules must state {RULE_ID}; found cutoff {rules.get('cutoff')!r}")
    era_rows = {row["document_id"]: row for _, row in iter_jsonl(_resolve(production, root, ERA_MANIFEST))}
    path_rows = {row["document_id"]: row for _, row in iter_jsonl(_resolve(production, root, PATH_MANIFEST))}
    if path_rows.keys() != era_rows.keys():
        errors.append("DOHA era and path manifests cover different decisions")
    bad: collections.defaultdict[str, list[str]] = collections.defaultdict(list)
    for identity, row in era_rows.items():
        era = row.get("sead4_era")
        if era not in ERAS or row.get("current_group") != ERAS[era] or row.get("retrieval_priority") != PRIORITY[era]:
            bad["era label, group and priority disagree"].append(identity)
            continue
        decided = row.get("decision_date")
        if decided and era_for(date.fromisoformat(decided)) != era:
            bad["era does not follow the decision date"].append(identity)
        if row.get("era_rule") != RULE_ID or not row.get("era_basis"):
            bad["era carries no rule or basis"].append(identity)
        other = path_rows.get(identity, {})
        if any(other.get(key) != row.get(key) for key in ("sead4_era", "current_group", "decision_date", "source_url")):
            bad["path manifest disagrees with the era manifest"].append(identity)
        url = row.get("source_url")
        if url is not None and (not str(url).startswith("https://doha.ogc.osd.mil/")
                                or row.get("source_url_basis") not in PROVENANCE_BASES):
            bad["source_url is not a recorded official DOHA URL"].append(identity)
    expected = {identity: (row.get("current_group"), row.get("retrieval_priority")) for identity, row in era_rows.items()}
    for relative, query in ((PATHS, "SELECT document_id,current_group,authority_priority FROM current_paths"),
                            (CONTENT, "SELECT document_id,current_group,retrieval_priority FROM decisions")):
        with contextlib.closing(_read_only(_resolve(production, root, relative))) as db:
            for identity, group, priority in db.execute(query):
                if expected.get(identity) != (group, priority):
                    bad[f"{relative} disagrees with the era manifest"].append(identity)
            if relative == CONTENT:
                for identity, group in db.execute("SELECT document_id,current_group FROM corpus"):
                    if (expected.get(identity) or (None,))[0] != group:
                        bad[f"{relative} corpus disagrees with the era manifest"].append(identity)
    for _, record in iter_jsonl(_resolve(production, root, DOCUMENTS)):
        if record.get("collection_id") == "doha_decisions" and record.get("document_id") in expected:
            group = expected[record["document_id"]][0]
            if record.get("current_group") != group or record.get("doha_group", group) != group:
                bad["documents.jsonl disagrees with the era manifest"].append(record["document_id"])
    if enriched is not None and enriched.is_file():
        for _, record in iter_jsonl(enriched):
            metadata = record.get("doha_case_metadata")
            if isinstance(metadata, dict) and record.get("document_id") in expected:
                if metadata.get("current_group") != expected[record["document_id"]][0]:
                    bad["enriched manifest disagrees with the era manifest"].append(record["document_id"])
    if recompute:
        fresh = {row["document_id"]: row for row in classify_rows(root, reviews or {}, provenance or {}, production)}
        for identity, row in era_rows.items():
            again = fresh.get(identity)
            if again is None or (again["sead4_era"], again["decision_date"]) != (row.get("sead4_era"), row.get("decision_date")):
                bad["era differs from the decision-date classification"].append(identity)
    for problem, identities in bad.items():
        errors.append(f"DOHA {problem}: {len(identities)} decisions, e.g. {', '.join(sorted(identities)[:5])}")
    return errors
