"""Turn a Librarian DOHA acquisition run into hash-bound intake plans.

The Librarian's doha-acquire leaves each decision in quarantine with its
.intake.json package. This reads those, extracts each PDF's text with
pdftotext -layout (the form of the library's existing DOHA robot text), and
derives the doha_review metadata from the decision text alone:

- identity: the CASENO header or the caption case number must match the listing
  label the Librarian fetched it under;
- decision date and era: doha_era.classify, the rule the release build applies;
- outcome: the decision's own conclusion or order, which must be unambiguous;
- topics: the KEYWORD line, read through the reviewed taxonomy's labels and
  aliases, or failing that the formal findings;
- answer eligibility: the rule review_metadata enforces.

Every value records the text it came from. A decision a rule cannot settle goes
to exceptions.jsonl for review instead of the plan; nothing is guessed, and no
filename is read as evidence. The output is a directory stage_intake accepts as
it is: sources/, text/, intake-plan.json, provenance rows for
decisions/doha_source_urls.jsonl, exceptions and a summary.

Reads the library and quarantine only; writes only to the output directory.
"""
from __future__ import annotations

import collections
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Iterable

from .common import iter_jsonl, read_json, sha256_file, utc_now, write_json, write_jsonl
from .doha import MANIFEST as DOHA_MANIFEST, TAXONOMY, validate_taxonomy
from .doha_era import classify

REVIEWER = "doha-intake-plan rule-based review v1"
PROVENANCE_BASIS = "acquisition_bytes_identical"
DOCUMENTS = "ROBOT_READABLE_DIRECTORY/MANIFESTS/documents.jsonl"
HUMAN_ROOT = "HUMAN_READABLE_DIRECTORY/PERSONNEL_VETTING/DOHA_DECISIONS"
ROBOT_ROOT = "ROBOT_READABLE_DIRECTORY/TEXT/PERSONNEL_VETTING/DOHA_DECISIONS"
ERA_FOLDERS = {"post_sead4": "POST_SEAD_4", "pre_sead4": "PRE_SEAD_4"}
AUTHORITY_TIER = 5  # what the library's existing DOHA records carry

KEY = re.compile(r"^(?P<case>\d{2}-\d{4,6})(?P<suffix>-[a-z0-9]+)?\.(?P<level>[ha][1-9])$")
CASENO = re.compile(r"^\s*CASENO:\s*(\d{2})-(\d{4,6})\.?([ha]\d)?\s*$", re.M | re.I)
# Older decisions converted from HTML open (and page-foot) with the bare key, e.g. "97-0050.h1".
BARE_KEY = re.compile(r"^\s*(\d{2})-(\d{4,6})\.([ha]\d)\s*$", re.M | re.I)
# "ISCR Case No. 12-09565", and in the 1990s "ISCR OSD Case No. 97-0050".
CAPTION = re.compile(r"(?:D?ISCR|ADP)(?:\s+OSD)?\s+Case\s+No\.?:?\s*(\d{2})-(\d{4,6})", re.I)
KEYWORD = re.compile(r"^\s*KEYWORD:\s*(.+)$", re.M | re.I)
# "Guideline F" since 1997; "Criterion F" in earlier decisions. The letters mean the same.
GUIDELINE_LETTER = re.compile(r"\b(?:Guideline|Criterion)\s+([A-M])\b")
FORMAL_FINDING = re.compile(r"(?:Guideline|Criterion)\s+([A-M])\b[^\n:]{0,60}:\s*(?:FOR|AGAINST)\s+APPLICANT", re.I)
# "security concerns under Guidelines F and E", "under Guideline F (Financial Considerations)".
SOR_GUIDELINES = re.compile(r"\b(?:Guidelines?|Criteri(?:on|a))\s+([A-M])\b((?:\s*(?:\([^)]{0,40}\))?\s*(?:,|and|&)\s*"
                            r"(?:Guidelines?\s+)?[A-M]\b)*)")
CONCLUSION_HEADING = re.compile(r"^\s*Conclusions?\s*$", re.M | re.I)

# Hearing conclusions, matched on whitespace-collapsed text so "not" split from
# "clearly" by a line break still counts. Every match is collected and the
# decision must point one way.
HEARING_OUTCOMES = (
    (re.compile(r"\bnot clearly consistent with the (?:interests? of )?national (?:security|interest)", re.I), "denied"),
    (re.compile(r"(?<!not )\bclearly consistent with the (?:interests? of )?national (?:security|interest) to (?:grant|continue)", re.I), "approved"),
    (re.compile(r"\b(?:eligibility|clearance|access)[^.]{0,80}?\b(?:is|are) (granted|denied|revoked|continued)\b", re.I), None),
)
# The boilerplate that opens every decision: "DOHA could not make the preliminary
# affirmative finding ... that it is clearly consistent ... to grant". Not an outcome.
BOILERPLATE = re.compile(r"affirmative finding|could not make|unable to find", re.I)
# "Adverse decision affirmed"; "the decision of the Administrative Judge denying Applicant a
# security clearance is AFFIRMED".
APPEAL_EXPLICIT = re.compile(
    r"\b(adverse|unfavorable|favorable)\s+(?:security\s+clearance\s+)?(?:decision|determination)\s+(?:is\s+)?"
    r"(affirmed|reversed|remanded)\b", re.I)
APPEAL_DIRECTED = re.compile(
    r"\bdecision\s+of\s+the\s+Administrative\s+Judge\s+(denying|granting|revoking|continuing)\b[^.]{0,120}?\bis\s+"
    r"(affirmed|reversed|remanded)\b", re.I)
# "The Decision is AFFIRMED." Its meaning depends on who appealed.
APPEAL_BARE = re.compile(r"\b(?:the\s+)?(?:Administrative\s+)?(?:Judge'?s\s+)?decision(?:\s+below)?\s+is\s+"
                         r"(affirmed|reversed|remanded)\b", re.I)
APPELLANT_APPLICANT = re.compile(r"\bApplicant\s+(?:has\s+)?(?:timely\s+)?appealed\b|\bApplicant's\s+appeal\b", re.I)
APPELLANT_GOVERNMENT = re.compile(r"\b(?:Department\s+Counsel|the\s+Government)\s+(?:has\s+)?(?:timely\s+)?appealed\b"
                                  r"|\b(?:Department\s+Counsel's|Government's)\s+appeal\b", re.I)
APPEAL_MEANING = {("adverse", "affirmed"): "denied", ("adverse", "reversed"): "approved",
                  ("favorable", "affirmed"): "approved", ("favorable", "reversed"): "denied"}
DIRECTION = {"denying": "adverse", "revoking": "adverse", "granting": "favorable", "continuing": "favorable"}
WORD_OUTCOME = {"granted": "approved", "continued": "approved", "denied": "denied", "revoked": "denied"}


def pdftotext_extractor(binary: str | None = None) -> Callable[[Path, Path], None]:
    tool = binary or shutil.which("pdftotext")
    if not tool:
        raise SystemExit("pdftotext (Poppler) is required: install it or pass --pdftotext <path>")

    def extract(source: Path, target: Path) -> None:
        subprocess.run([tool, "-layout", "-enc", "UTF-8", str(source), str(target)], check=True,
                       capture_output=True, timeout=300)
    return extract


def _snippet(text: str, match: re.Match[str], width: int = 90) -> str:
    return re.sub(r"\s+", " ", text[max(0, match.start() - 10):match.end() + 10]).strip()[:width]


def identity(text: str, case_id: str, level: str) -> tuple[str | None, str]:
    """Problem, or None, and the evidence. The text must name the listed case."""
    number = int(case_id.split("-")[1])
    year = case_id.split("-")[0]
    for pattern, name in ((CASENO, "CASENO header"), (BARE_KEY, "case key line")):
        header = pattern.search(text[:20000])
        if header:
            same = header.group(1) == year and int(header.group(2)) == number
            if not same or (header.group(3) and header.group(3).lower() != level):
                return f"{name} '{_snippet(text, header)}' does not match {case_id}.{level}", ""
            return None, f"{name} '{header.group(0).strip()}'"
    caption = CAPTION.search(text[:20000])
    if caption:
        if caption.group(1) != year or int(caption.group(2)) != number:
            return f"caption '{_snippet(text, caption)}' does not match {case_id}", ""
        return None, f"caption '{caption.group(0).strip()}'; level {level} from the official listing label"
    return "no case number found in the extracted text", ""


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _appeal_outcome(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    flat = _flat(text)
    for match in APPEAL_EXPLICIT.finditer(flat):
        kind, verb = match.group(1).lower(), match.group(2).lower()
        kind = "adverse" if kind == "unfavorable" else kind
        found.setdefault("remanded" if verb == "remanded" else APPEAL_MEANING[(kind, verb)], match.group(0))
    for match in APPEAL_DIRECTED.finditer(flat):
        verb = match.group(2).lower()
        found.setdefault("remanded" if verb == "remanded" else APPEAL_MEANING[(DIRECTION[match.group(1).lower()], verb)],
                         _snippet(flat, match, 160))
    if found:
        return found
    bare = {match.group(1).lower(): match.group(0) for match in APPEAL_BARE.finditer(flat)}
    if list(bare) == ["remanded"]:
        return {"remanded": bare["remanded"]}
    if len(bare) == 1:
        (verb, said), = bare.items()
        applicant, government = bool(APPELLANT_APPLICANT.search(flat)), bool(APPELLANT_GOVERNMENT.search(flat))
        if applicant != government:
            kind = "adverse" if applicant else "favorable"
            found[APPEAL_MEANING[(kind, verb)]] = f"'{said}' on an appeal by {'Applicant' if applicant else 'Department Counsel'}"
    return found


def _hearing_outcome(text: str) -> dict[str, str]:
    headings = list(CONCLUSION_HEADING.finditer(text))
    region = _flat(text[headings[-1].start():] if headings else text[-3000:])
    found: dict[str, str] = {}
    for pattern, value in HEARING_OUTCOMES:
        for match in pattern.finditer(region):
            sentence = region[region.rfind(". ", 0, match.start()) + 1:match.start()]
            if BOILERPLATE.search(sentence):
                continue
            found.setdefault(value or WORD_OUTCOME[match.group(1).lower()], match.group(0))
    return found


def outcome(text: str, level: str) -> tuple[str | None, str]:
    """(outcome, evidence) or (None, problem). Ambiguity is a problem, not a guess."""
    found = _appeal_outcome(text) if level.startswith("a") else _hearing_outcome(text)
    if len(found) == 1:
        (value, evidence), = found.items()
        return value, evidence[:160]
    if not found:
        return None, "no conclusion or order states the outcome"
    return None, "conflicting outcome statements: " + "; ".join(f"{k} ('{v[:80]}')" for k, v in sorted(found.items()))


def topics(text: str, taxonomy: dict[str, Any]) -> tuple[list[str], str]:
    """KEYWORD line first; then formal findings; then the guidelines the SOR alleged."""
    guidelines = validate_taxonomy(taxonomy)
    line = KEYWORD.search(text[:20000])
    if line:
        keywords = line.group(1)
        codes = set(GUIDELINE_LETTER.findall(keywords))
        lowered = keywords.lower()
        for code, item in guidelines.items():
            names = [item.get("label", "")] + list(item["aliases"])
            if any(name and re.search(r"\b" + re.escape(name.lower()) + r"\b", lowered) for name in names):
                codes.add(code)
        if codes:
            return sorted(codes), f"KEYWORD line '{keywords.strip()[:120]}'"
    findings = sorted(set(code.upper() for code in FORMAL_FINDING.findall(text)))
    if findings:
        return findings, "formal findings for " + ", ".join(f"Guideline {code}" for code in findings)
    # The Statement of the Case names the guidelines the SOR alleged.
    opening = _flat(text[:8000])
    alleged: set[str] = set()
    for match in SOR_GUIDELINES.finditer(opening):
        alleged.add(match.group(1))
        alleged.update(re.findall(r"\b([A-M])\b", match.group(2)))
    alleged &= set(guidelines)
    if alleged:
        return sorted(alleged), "guidelines alleged in the Statement of the Case"
    return [], "no KEYWORD line, formal findings or SOR guidelines name a guideline"


def load_packages(run_dir: Path) -> tuple[list[tuple[Path, dict[str, Any]]], list[tuple[Path, str]]]:
    """Readable packages, and the ones that are not. An acquisition run interrupted
    mid-write can leave an empty package; that is one decision to refetch, not a
    reason to stop."""
    packages, unreadable = [], []
    for group in ("iscr-hearing-decisions", "doha-appeal-board-decisions"):
        for path in sorted((run_dir / group).glob("*.intake.json")):
            try:
                package = read_json(path)
                if not isinstance(package, dict) or not package.get("source_filename"):
                    raise ValueError("not an intake package")
            except (ValueError, UnicodeDecodeError) as exc:
                unreadable.append((path, f"{type(exc).__name__}: {exc}"))
                continue
            packages.append((path, package))
    return packages, unreadable


def _rows(path: Path) -> list[dict[str, Any]]:
    """A JSON-lines input, with the file named if it does not parse."""
    try:
        return [row for _, row in iter_jsonl(path)]
    except ValueError as exc:
        raise ValueError(f"{path} is not valid JSON lines: {exc}") from exc


def held_cases(library: Path) -> tuple[set[str], set[str], set[str]]:
    """Case keys, document IDs and paths the library already holds."""
    cases, ids, paths = set(), set(), set()
    if (library / DOHA_MANIFEST).is_file():
        for row in _rows(library / DOHA_MANIFEST):
            cases.add(str(row.get("case_stem", "")).split("_")[0].lower())
    for row in _rows(library / DOCUMENTS):
        ids.add(row["document_id"])
        for key in ("human_source_path", "robot_text_path"):
            if row.get(key):
                paths.add(str(row[key]).replace("\\", "/").casefold())
    return cases, ids, paths


def pilot_sample(keys: list[str], size: int) -> list[str]:
    """Spread a pilot across hearing/appeal and docket decades, deterministically."""
    buckets: dict[tuple[str, str], list[str]] = collections.defaultdict(list)
    for key in sorted(keys):
        decade = key[:1]
        buckets[(key.rsplit(".", 1)[1][0], decade)].append(key)
    chosen, queues = [], [buckets[b] for b in sorted(buckets)]
    while len(chosen) < size and any(queues):
        for queue in queues:
            if queue and len(chosen) < size:
                chosen.append(queue.pop(len(queue) // 2))
    return chosen


def build_plan(library: Path, run_dir: Path, not_held: Path, out_dir: Path,
               extract: Callable[[Path, Path], None], *, group: str | None = None, era: str | None = None,
               limit: int | None = None, pilot: int | None = None) -> dict[str, Any]:
    if out_dir.exists():
        raise FileExistsError(f"output directory already exists: {out_dir}")
    try:
        taxonomy = read_json(library / TAXONOMY)
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read the DOHA taxonomy at {library / TAXONOMY}; check --library-root: {exc}") from exc
    validate_taxonomy(taxonomy)
    listings = {row["case_key"]: row for row in _rows(not_held)}
    held, used_ids, used_paths = held_cases(library)
    packages = {}
    loaded, unreadable = load_packages(run_dir)
    for path, package in loaded:
        packages[Path(package["source_filename"]).stem.lower()] = (path, package)
    keys = sorted(packages)
    if group:
        keys = [k for k in keys if k.rsplit(".", 1)[1].startswith("h" if group == "hearings" else "a")]
    if pilot:
        keys = pilot_sample(keys, pilot)
    for sub in ("sources", "text"):
        (out_dir / sub).mkdir(parents=True)
    items, provenance, exceptions = [], [], []
    counts: collections.Counter[str] = collections.Counter()
    reviewed_utc = utc_now()
    for path, problem in unreadable:
        counts["exception"] += 1
        exceptions.append({"case_key": path.name.removesuffix(".pdf.intake.json").lower(),
                           "reason": f"intake package unreadable ({problem}); refetch this decision",
                           "package": str(path)})

    def refuse(key: str, reason: str, **extra: Any) -> None:
        counts["exception"] += 1
        exceptions.append(dict(case_key=key, reason=reason, **extra))

    for key in keys:
        if limit and len(items) >= limit:
            break
        package_path, package = packages[key]
        parsed = KEY.match(key)
        if not parsed or parsed.group("suffix"):
            refuse(key, "case key has a suffix or does not parse; needs manual identity review")
            continue
        case_id, level = parsed.group("case"), parsed.group("level")
        if key in held:
            counts["already_held"] += 1
            continue
        source = package_path.with_name(package["source_filename"])
        if sha256_file(source) != package["source_sha256"]:
            refuse(key, "quarantined source does not match its package hash")
            continue
        text_path = out_dir / "text" / f"{key}.txt"
        try:
            extract(source, text_path)
        except Exception as exc:  # a failed extraction is an exception to review, not a stop
            refuse(key, f"extraction failed: {type(exc).__name__}: {exc}")
            continue
        text = text_path.read_text(encoding="utf-8", errors="replace") if text_path.is_file() else ""
        if len(text.strip()) < 200:
            text_path.unlink(missing_ok=True)
            refuse(key, "no usable text layer (likely a scan); needs OCR", characters=len(text.strip()))
            continue
        problem, identity_basis = identity(text, case_id, level)
        if problem:
            refuse(key, problem)
            continue
        listing = listings.get(key, {})
        titles = sorted(set(listing.get("listing_titles", [])))
        era_result = classify(text, case_id, listing_title=titles[0] if len(titles) == 1 else None)
        decided = era_result.get("decision_date")
        if era_result["sead4_era"] not in ERA_FOLDERS or not decided:
            refuse(key, f"decision date not established: {era_result.get('era_basis')}",
                   date_basis=era_result.get("decision_date_basis"), conflicts=era_result.get("date_conflicts"))
            continue
        if era and era_result["sead4_era"] != era:
            counts["outside_requested_era"] += 1
            text_path.unlink(missing_ok=True)
            continue
        result, outcome_basis = outcome(text, level)
        if result is None:
            refuse(key, outcome_basis)
            continue
        codes, topic_basis = topics(text, taxonomy)
        group_name = ERA_FOLDERS[era_result["sead4_era"]]
        eligible = group_name == "POST_SEAD_4" and level.startswith("h") and result in ("approved", "denied") and bool(codes)
        stem = f"{case_id}.{level}_{result}" + "".join(f"_{code}" for code in codes)
        document_id = f"dcsa-doha_decisions-pdf-s-{case_id}-{level}_{result}" + "".join(f"_{c.lower()}" for c in codes)
        human = f"{HUMAN_ROOT}/{group_name}/{stem}.pdf"
        robot = f"{ROBOT_ROOT}/{group_name}/{stem}.txt"
        if document_id in used_ids or human.casefold() in used_paths or robot.casefold() in used_paths:
            refuse(key, f"document ID or path already in use: {document_id}")
            continue
        used_ids.add(document_id)
        used_paths.update({human.casefold(), robot.casefold()})
        shutil.copy2(source, out_dir / "sources" / source.name)
        shutil.copy2(package_path, out_dir / "sources" / package_path.name)
        robot_sha = sha256_file(text_path)
        basis = (f"identity: {identity_basis}; date: {decided} ({era_result.get('decision_date_basis')}); "
                 f"outcome: {outcome_basis}; topics: {topic_basis}")
        items.append({
            "package": f"sources/{package_path.name}",
            "robot_file": f"text/{text_path.name}",
            "robot_sha256": robot_sha,
            "record": {
                "document_id": document_id, "collection_id": "doha_decisions", "domain": "personnel_vetting",
                "authority_tier": AUTHORITY_TIER, "current_status": "historical_case_research",
                "human_source_path": human, "robot_text_path": robot,
                "title": f"DOHA Decision {stem.upper()}", "document_type": "DOHA decision",
                "doha_review": {
                    "case_id": case_id, "decision_level": level, "decision_date": decided,
                    "current_group": group_name, "outcome": result, "guidelines": codes,
                    "answer_eligible": eligible, "reviewed_by": REVIEWER, "reviewed_utc": reviewed_utc,
                    "metadata_basis": basis,
                },
            },
            "review": {
                "reviewed_by": REVIEWER, "reviewed_utc": reviewed_utc,
                "identity": f"Text names {case_id}.{level}: {identity_basis}; matches official listing label "
                            f"{package.get('publisher_claim')!r}.",
                "provenance": f"Fetched by the Librarian from {package['resolved_source_uri']} at {package['retrieved_at']}; "
                              f"source sha256 {package['source_sha256']} verified against the quarantined bytes.",
                "extraction": f"pdftotext -layout of the exact quarantined bytes; {len(text):,} characters; "
                              "case number found in the text.",
                "parity": "Robot text is the complete extraction of the retained PDF; nonempty and hash-bound.",
                "taxonomy": f"doha_decisions, {group_name} by decision date {decided}; topics {codes or 'none'} from {topic_basis}.",
                "lifecycle": "historical_case_research: a DOHA decision is case research, never current guidance.",
            },
        })
        urls = listing.get("urls_by_format", {}).get("pdf") or [package["requested_source_uri"]]
        provenance.append({
            "document_id": document_id, "case_key": key, "source_url": package["resolved_source_uri"],
            "source_url_basis": PROVENANCE_BASIS, "source_bytes_sha256": package["source_sha256"],
            "source_listing_page": package["resolved_source_uri"].split("FileId/")[0],
            "source_listing_title": titles[0] if len(titles) == 1 else None,
            "source_listing_captured_utc": listing.get("captured_utc"),
            "source_url_alternates": sorted(set(urls) - {package["resolved_source_uri"]}),
            "listing_conflict": len(titles) > 1,
        })
        counts["planned"] += 1
        counts[f"{group_name}/{'hearing' if level[0] == 'h' else 'appeal'}/{result}"] += 1
        counts["answer_eligible"] += eligible
    if items:
        write_json(out_dir / "intake-plan.json", {"schema_version": "1.0", "items": items})
    write_jsonl(out_dir / "doha_source_urls.additions.jsonl", provenance)
    write_jsonl(out_dir / "exceptions.jsonl", exceptions)
    summary = {"schema_version": "1.0", "generated_utc": reviewed_utc, "run_dir": str(run_dir),
               "library_root": str(library), "reviewer": REVIEWER, "selection":
               {"group": group, "era": era, "limit": limit, "pilot": pilot},
               "counts": dict(sorted(counts.items())), "library_written": False,
               "owner_signoff": "required before publish: spot-check a sample of plan items against their PDFs"}
    write_json(out_dir / "summary.json", summary)
    return summary
