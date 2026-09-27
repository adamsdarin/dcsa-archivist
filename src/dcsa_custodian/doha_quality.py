"""Measure and stage DOHA intake: batches, accuracy samples, scoring, and a re-check of held decisions.

A plan from doha-intake-plan is only as good as its rules, and passing validate
proves the release is consistent, not that a decision labelled denied was denied.
These tools turn that into a measured claim:

- split_plan: divide a large plan into batches stage_intake accepts, keeping every
  decision of a case in the same batch so appeal/hearing links stay inside it;
- accuracy_sample: a seeded, stratified random sample of a plan (or of the held
  library) as a sheet the owner checks against the PDFs;
- score_sheet: the error rate of a checked sheet and its one-sided 95% upper bound,
  passed only when that bound is at or under the agreed target;
- recheck_library: run the intake rules over the decisions the library already
  holds, list every disagreement with the stored outcome or topics, and propose
  the appeal fields those decisions lack;
- append_provenance: add a batch's provenance rows to decisions/doha_source_urls.jsonl,
  refusing any row that conflicts with one already recorded.

Everything reads the library and plans only; nothing here writes the library.
"""
from __future__ import annotations

import collections
import contextlib
import csv
import math
import os
import random
import shutil
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .common import iter_jsonl, read_json, sha256_file, utc_now, write_json, write_jsonl
from .doha import CONTENT, MANIFEST as PATH_MANIFEST, TAXONOMY, validate_taxonomy
from .doha_bulk import REMAND_TEXT, appeal_ruling, outcome, remanded_from, reviewed_decision, topics

CHECK_FIELDS = ("date_ok", "outcome_ok", "appeal_ok", "topics_ok")
SHEET_COLUMNS = ("sample_id", "purpose", "stratum", "case_key", "pdf", "decision_date", "era", "ruling",
                 "appeal_disposition", "appealed_by", "reviewed_decision", "guidelines", "evidence",
                 *CHECK_FIELDS, "notes")
VERDICTS = ("library", "rule", "neither")
DISAGREEMENT_COLUMNS = ("sample_id", "case_key", "field", "library_value", "rule_value", "rule_evidence",
                        "pdf", "verdict", "notes")
CONFIDENCE = 0.95


# ---------------------------------------------------------------- batches

def _link_or_copy(source: Path, target: Path) -> None:
    """A hard link where the file system allows one (no second copy on disk), else a copy."""
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def _plan_items(plan_dir: Path) -> list[dict[str, Any]]:
    path = plan_dir / "intake-plan.json"
    if not path.is_file():
        raise FileNotFoundError(f"no intake-plan.json in {plan_dir}")
    payload = read_json(path)
    if payload.get("schema_version") != "1.0" or not isinstance(payload.get("items"), list):
        raise ValueError(f"not an intake plan: {path}")
    return payload["items"]


def split_plan(plan_dir: Path, size: int, out_dir: Path) -> dict[str, Any]:
    """Batches of about ``size`` decisions; a case is never split across batches."""
    if size < 1:
        raise ValueError("batch size must be positive")
    if out_dir.exists():
        raise FileExistsError(f"output directory already exists: {out_dir}")
    items = _plan_items(plan_dir)
    additions = {row["document_id"]: row for _, row in iter_jsonl(plan_dir / "doha_source_urls.additions.jsonl")}
    cases: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for item in items:
        cases[item["record"]["doha_review"]["case_id"]].append(item)
    batches: list[list[dict[str, Any]]] = [[]]
    for case_id in sorted(cases):
        if len(batches[-1]) >= size:
            batches.append([])
        batches[-1].extend(cases[case_id])
    index = []
    for number, batch in enumerate(batches, 1):
        target = out_dir / f"batch-{number:02d}"
        for sub in ("sources", "text"):
            (target / sub).mkdir(parents=True)
        rows = []
        for item in batch:
            robot = plan_dir / item["robot_file"]
            if sha256_file(robot) != item["robot_sha256"]:
                raise ValueError(f"robot text changed since planning: {robot}")
            package_path = plan_dir / item["package"]
            source = package_path.with_name(read_json(package_path)["source_filename"])
            for path in (package_path, source, robot):
                _link_or_copy(path, target / path.relative_to(plan_dir))
            document_id = item["record"]["document_id"]
            if document_id not in additions:
                raise ValueError(f"plan has no provenance row for {document_id}")
            rows.append(additions[document_id])
        write_json(target / "intake-plan.json", {"schema_version": "1.0", "items": batch})
        write_jsonl(target / "doha_source_urls.additions.jsonl", rows)
        write_jsonl(target / "exceptions.jsonl", [])
        summary = {"schema_version": "1.0", "batch": number, "of": len(batches), "from_plan": str(plan_dir),
                   "decisions": len(batch), "cases": len({i["record"]["doha_review"]["case_id"] for i in batch}),
                   "library_written": False,
                   "owner_signoff": "required before publish: spot-check this batch against its PDFs"}
        write_json(target / "summary.json", summary)
        index.append({"batch": target.name, "decisions": summary["decisions"], "cases": summary["cases"]})
    report = {"schema_version": "1.0", "generated_utc": utc_now(), "from_plan": str(plan_dir),
              "batch_size": size, "decisions": len(items), "batches": index}
    write_json(out_dir / "batches.json", report)
    return report


# ---------------------------------------------------------------- sampling

def _stratum(row: dict[str, Any]) -> str:
    family = "appeal" if row["case_key"].split(".")[1].startswith("a") else "hearing"
    return f"{family}/{row['era']}/{row['appeal_disposition'] or row['ruling']}"


def allocate(sizes: dict[str, int], total: int) -> dict[str, int]:
    """Proportional allocation by largest remainder, so the sample mirrors the population."""
    population = sum(sizes.values())
    if not population:
        return {}
    total = min(total, population)
    exact = {k: total * n / population for k, n in sizes.items()}
    share = {k: int(v) for k, v in exact.items()}
    for key in sorted(exact, key=lambda k: (-(exact[k] - share[k]), k))[:total - sum(share.values())]:
        share[key] += 1
    return share


def draw(rows: list[dict[str, Any]], size: int, edge: int, seed: int) -> list[dict[str, Any]]:
    """An estimate sample proportional to each stratum, then up to ``edge`` extra draws for
    each stratum the estimate barely touches. Edge rows are checked but never scored into
    the estimate: over-sampling rare rulings would bias it."""
    rng = random.Random(seed)
    strata: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in sorted(rows, key=lambda r: r["case_key"]):
        strata[_stratum(row)].append(row)
    shares = allocate({k: len(v) for k, v in strata.items()}, size)
    chosen = []
    for key in sorted(strata):
        pool = strata[key][:]
        rng.shuffle(pool)
        take = shares.get(key, 0)
        chosen += [dict(row, purpose="estimate", stratum=key) for row in pool[:take]]
        extra = max(0, min(edge - take, len(pool) - take))
        chosen += [dict(row, purpose="edge", stratum=key) for row in pool[take:take + extra]]
    for number, row in enumerate(chosen, 1):
        row["sample_id"] = number
    return chosen


def _describe(review: dict[str, Any]) -> dict[str, str]:
    level = review["decision_level"]
    ruling = review["outcome"]
    if level.startswith("h"):
        ruling = {"approved": "granted"}.get(ruling, ruling)
    reviewed = review.get("reviewed_decision") or {}
    link = ""
    if level.startswith("a"):
        link = f"{reviewed.get('case_key') or 'not identified'} ({reviewed.get('outcome') or 'outcome not stated'})"
    elif review.get("decided_on_remand_from"):
        link = f"on remand from {review['decided_on_remand_from'].get('case_key') or 'not identified'}"
    return {"case_key": f"{review['case_id']}.{level}", "decision_date": review.get("decision_date") or "",
            "era": review.get("current_group") or "", "ruling": ruling,
            "appeal_disposition": review.get("appeal_disposition") or "",
            "appealed_by": review.get("appealed_by") or "", "reviewed_decision": link,
            "guidelines": ",".join(review.get("guidelines") or [])}


def plan_rows(plan_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for item in _plan_items(plan_dir):
        review = item["record"]["doha_review"]
        package_path = plan_dir / item["package"]
        pdf = package_path.with_name(read_json(package_path)["source_filename"])
        evidence = review.get("metadata_basis", "").split("outcome: ", 1)[-1].split("; topics:", 1)[0]
        rows.append({**_describe(review), "pdf": str(pdf.resolve()), "evidence": evidence[:200]})
    return rows


def write_sheet(rows: list[dict[str, Any]], path: Path, columns: Iterable[str] = SHEET_COLUMNS) -> None:
    columns = list(columns)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8-sig", newline="") as handle:  # utf-8-sig: Excel reads it as UTF-8
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def accuracy_sample(plan_dir: Path, out: Path, size: int = 150, edge: int = 3, seed: int = 20260927) -> dict[str, Any]:
    rows = draw(plan_rows(plan_dir), size, edge, seed)
    write_sheet(rows, out)
    purposes = collections.Counter(r["purpose"] for r in rows)
    return {"sheet": str(out), "seed": seed, "estimate": purposes["estimate"], "edge": purposes["edge"],
            "strata": dict(sorted(collections.Counter(r["stratum"] for r in rows).items()))}


# ---------------------------------------------------------------- scoring

def _binomial_cdf(k: int, n: int, p: float) -> float:
    if p <= 0:
        return 1.0
    if p >= 1:
        return 1.0 if k >= n else 0.0
    return sum(math.exp(math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1)
                        + i * math.log(p) + (n - i) * math.log1p(-p)) for i in range(k + 1))


def upper_bound(errors: int, n: int, confidence: float = CONFIDENCE) -> float:
    """One-sided Clopper-Pearson upper bound: the highest error rate still consistent with
    seeing this few errors, at the given confidence."""
    if n == 0:
        return 1.0
    if errors >= n:
        return 1.0
    low, high = errors / n, 1.0
    for _ in range(80):
        mid = (low + high) / 2
        if _binomial_cdf(errors, n, mid) > 1 - confidence:
            low = mid
        else:
            high = mid
    return high


def _mark(value: str, column: str, row: dict[str, str]) -> str:
    mark = (value or "").strip().upper()
    mark = {"YES": "Y", "NO": "N", "N/A": "NA", "": ""}.get(mark, mark)
    if mark == "" and column == "appeal_ok" and not row.get("appeal_disposition"):
        return "NA"  # a hearing has no appeal fields to check
    if mark not in ("Y", "N", "NA"):
        raise ValueError(f"sample {row.get('sample_id')}: {column} must be Y, N or NA, not {value!r}")
    return mark


def score_sheet(path: Path, target: float) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except UnicodeDecodeError:  # Excel's plain "CSV" save on Windows writes the ANSI code page
        with path.open(encoding="cp1252", newline="") as handle:
            rows = list(csv.DictReader(handle))
    if rows and "verdict" in rows[0]:
        return _score_disagreements(path, rows)
    fields: dict[str, collections.Counter[str]] = {c: collections.Counter() for c in CHECK_FIELDS}
    estimate = errors = 0
    wrong, edge_wrong = [], []
    for row in rows:
        marks = {c: _mark(row.get(c, ""), c, row) for c in CHECK_FIELDS}
        for column, mark in marks.items():
            fields[column][mark] += 1
        bad = [c.removesuffix("_ok") for c, m in marks.items() if m == "N"]
        entry = {"sample_id": row["sample_id"], "case_key": row["case_key"], "wrong": bad, "notes": row.get("notes", "")}
        if row.get("purpose") == "edge":
            if bad:
                edge_wrong.append(entry)
            continue
        estimate += 1
        if bad:
            errors += 1
            wrong.append(entry)
    bound = upper_bound(errors, estimate)
    return {"sheet": str(path), "decisions_scored": estimate, "decisions_wrong": errors,
            "error_rate": round(errors / estimate, 4) if estimate else None,
            "upper_bound_95": round(bound, 4), "target": target, "passed": bool(estimate) and bound <= target,
            "meaning": (f"with 95% confidence at most {bound:.1%} of the decisions are wrong in at least one "
                        f"checked field; the target is {target:.1%}"),
            "fields": {c: dict(v) for c, v in fields.items()}, "wrong": wrong,
            "edge_rows_wrong": edge_wrong}


def _score_disagreements(path: Path, rows: list[dict[str, str]]) -> dict[str, Any]:
    tally: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    for row in rows:
        verdict = (row.get("verdict") or "").strip().lower()
        if verdict not in VERDICTS:
            raise ValueError(f"sample {row.get('sample_id')}: verdict must be one of {', '.join(VERDICTS)}")
        tally[row["field"]][verdict] += 1
    return {"sheet": str(path), "checked": len(rows),
            "by_field": {field: dict(counts) for field, counts in sorted(tally.items())},
            "meaning": "'library' means the stored value was right and the rule wrong; 'rule' means the "
                       "library holds an error the re-check would correct; 'neither' means both are wrong"}


# ---------------------------------------------------------------- held library

def _held(library: Path) -> list[dict[str, Any]]:
    index = library / CONTENT
    if not index.is_file():
        raise FileNotFoundError(f"no DOHA index at {index}; check --library-root")
    uri = index.resolve().as_uri() + "?mode=ro"
    with contextlib.closing(sqlite3.connect(uri, uri=True)) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute(
            "SELECT document_id, case_id, decision_level, outcome, guideline_codes, current_group, "
            "human_source_path, robot_text_path FROM decisions ORDER BY case_id, decision_level")]


def recheck_library(library: Path, out_dir: Path, not_held: Path | None = None,
                    sample_size: int = 150, disagreement_sample: int = 100, edge: int = 3,
                    seed: int = 20260927) -> dict[str, Any]:
    if out_dir.exists():
        raise FileExistsError(f"output directory already exists: {out_dir}")
    taxonomy = read_json(library / TAXONOMY)
    validate_taxonomy(taxonomy)
    held = _held(library)
    dates = {row["document_id"]: row.get("decision_date") for _, row in iter_jsonl(library / PATH_MANIFEST)}
    known: dict[str, tuple[str | None, str]] = {}
    if not_held:
        known.update({row["case_key"]: (None, "listed by DOHA, not held") for _, row in iter_jsonl(not_held)})
    for row in held:
        known[f"{row['case_id']}.{row['decision_level']}"] = (dates.get(row["document_id"]), "held by the library")
    out_dir.mkdir(parents=True)
    counts: collections.Counter[str] = collections.Counter()
    disagreements, unsettled, backfill, sheet_rows = [], [], [], []
    for row in held:
        key, level = f"{row['case_id']}.{row['decision_level']}", row["decision_level"]
        robot = library / row["robot_text_path"]
        pdf = str((library / row["human_source_path"]).resolve())
        try:
            text = robot.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            unsettled.append({"case_key": key, "document_id": row["document_id"], "field": "text",
                              "reason": f"robot text unreadable: {exc}"})
            counts["text_unreadable"] += 1
            continue
        stored_topics = sorted(filter(None, (row["guideline_codes"] or "").split(",")))
        decided = dates.get(row["document_id"]) or ""

        def differ(field: str, stored: Any, found: Any, evidence: str) -> None:
            counts[f"{field}_disagrees"] += 1
            disagreements.append({"case_key": key, "document_id": row["document_id"], "field": field,
                                  "library_value": stored, "rule_value": found, "rule_evidence": evidence[:200],
                                  "pdf": pdf})

        found, evidence = outcome(text, level)
        if found is None:
            counts["outcome_unsettled"] += 1
            unsettled.append({"case_key": key, "document_id": row["document_id"], "field": "outcome", "reason": evidence})
        elif found != row["outcome"]:
            differ("outcome", row["outcome"], found, evidence)
        else:
            counts["outcome_agrees"] += 1
        codes, topic_basis = topics(text, taxonomy)
        if not codes:
            counts["topics_unsettled"] += 1
            unsettled.append({"case_key": key, "document_id": row["document_id"], "field": "topics", "reason": topic_basis})
        elif codes != stored_topics:
            differ("topics", ",".join(stored_topics), ",".join(codes), topic_basis)
        else:
            counts["topics_agrees"] += 1
        review = {"case_id": row["case_id"], "decision_level": level, "decision_date": decided,
                  "current_group": row["current_group"], "outcome": row["outcome"], "guidelines": stored_topics}
        if level.startswith("a"):
            ruling = appeal_ruling(text)
            if "problem" in ruling:
                counts["appeal_unsettled"] += 1
                unsettled.append({"case_key": key, "document_id": row["document_id"], "field": "appeal",
                                  "reason": ruling["problem"]})
            else:
                link = {**reviewed_decision(row["case_id"], level, decided, known), "outcome": ruling["reviewed_outcome"]}
                fields = {"appeal_disposition": ruling["disposition"], "appealed_by": ruling["appealed_by"],
                          "reviewed_decision": link}
                backfill.append({"document_id": row["document_id"], "case_key": key, **fields,
                                 "evidence": ruling["evidence"]})
                review.update(fields)
                counts["appeal_backfilled"] += 1
        elif int(level[1:]) > 1 or REMAND_TEXT.search(text):
            link = remanded_from(row["case_id"], level, decided, known)
            if link and link.get("case_key"):
                backfill.append({"document_id": row["document_id"], "case_key": key, "decided_on_remand_from": link})
                review["decided_on_remand_from"] = link
                counts["remand_link_backfilled"] += 1
        sheet_rows.append({**_describe(review), "pdf": pdf, "evidence": evidence[:200] if found else ""})
        counts["decisions"] += 1
    rng = random.Random(seed)
    picked = sorted(rng.sample(disagreements, min(disagreement_sample, len(disagreements))),
                    key=lambda r: (r["field"], r["case_key"]))
    picked = [dict(row, sample_id=number) for number, row in enumerate(picked, 1)]
    write_jsonl(out_dir / "disagreements.jsonl", disagreements)
    write_jsonl(out_dir / "unsettled.jsonl", unsettled)
    write_jsonl(out_dir / "ruling_backfill.jsonl", backfill)
    write_sheet(picked, out_dir / "disagreements_sample.csv", DISAGREEMENT_COLUMNS)
    write_sheet(draw(sheet_rows, sample_size, edge, seed), out_dir / "existing_accuracy_sample.csv")
    summary = {"schema_version": "1.0", "generated_utc": utc_now(), "library_root": str(library),
               "counts": dict(sorted(counts.items())), "library_written": False,
               "note": ("Decision dates are not re-checked here: the release build already recomputes them with "
                        "the same rule and validate refuses a candidate where they disagree.")}
    write_json(out_dir / "summary.json", summary)
    return summary


# ---------------------------------------------------------------- provenance

def append_provenance(additions: Path, target: Path, dry_run: bool = False) -> dict[str, Any]:
    """Add a batch's provenance rows. A row already recorded identically is skipped; a
    different row for the same document is refused, never overwritten."""
    existing = {row["document_id"]: row for _, row in iter_jsonl(target)} if target.is_file() else {}
    new, same = [], 0
    for _, row in iter_jsonl(additions):
        recorded = existing.get(row["document_id"])
        if recorded is None:
            new.append(row)
            existing[row["document_id"]] = row
        elif recorded == row:
            same += 1
        else:
            raise ValueError(f"{target} already records different provenance for {row['document_id']}")
    if new and not dry_run:
        rows = [row for _, row in iter_jsonl(target)] if target.is_file() else []
        write_jsonl(target, rows + new)
    return {"target": str(target), "added": len(new), "already_recorded": same, "dry_run": dry_run}
