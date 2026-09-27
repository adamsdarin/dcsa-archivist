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

REVIEWER = "doha-intake-plan rule-based review v4"
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
# Older decisions write "AGAINST THE APPLICANT" / "For the Applicant".
FORMAL_FINDING = re.compile(r"(?:Guideline|Criterion)\s+([A-M])\b[^\n:]{0,60}:\s*(?:FOR|AGAINST)\s+(?:THE\s+)?APPLICANT", re.I)
# Formal findings without a colon, e.g. "Paragraph 1, Guideline F (Financial Considerations)   FOR APPLICANT".
# Upper case only, so running prose ("... for Applicant") does not count.
FORMAL_FINDING_COLUMN = re.compile(r"(?:Guideline|Criterion)\s+([A-M])\b[^\n]{0,60}?\s(?:FOR|AGAINST)\s+(?:THE\s+)?APPLICANT\b")
# "security concerns under Guidelines F and E", "under Guideline F (Financial Considerations)".
SOR_GUIDELINES = re.compile(r"\b(?i:guidelines?|criteri(?:on|a))\s+([A-M])\b((?:\s*(?:\([^)]{0,40}\))?\s*(?:,|and|&)\s*"
                            r"(?:Guidelines?\s+)?[A-M]\b)*)")
# Older decisions put the order under a bare "DECISION" heading after the formal findings;
# newer ones under "Conclusion". The last of either is the order (a newer decision's
# "Decision" title line comes first).
CONCLUSION_HEADING = re.compile(r"^\s*(?:Conclusions?|Decision)\s*$", re.M | re.I)

# Hearing conclusions, matched on whitespace-collapsed text so "not" split from
# "clearly" by a line break still counts. Every match is collected and the
# decision must point one way.
HEARING_OUTCOMES = (
    (re.compile(r"\bnot clearly consistent with the (?:interests? of )?national (?:security|interest)", re.I), "denied"),
    (re.compile(r"(?<!not )\bclearly consistent with the (?:interests? of )?national (?:security|interest)"
                r"(?: (?:interests? )?of the United States)? to (?:grant|continue)", re.I), "approved"),
    (re.compile(r"\b(?:eligibility|clearance|access)[^.]{0,80}?\b(?:is|are) (granted|denied|revoked|continued)\b", re.I), None),
)
# The boilerplate that opens every decision: "DOHA could not make the preliminary
# affirmative finding ... that it is clearly consistent ... to grant". Not an outcome.
# Also the burden-of-proof sentence: "the ultimate burden of persuasion in proving that it is
# clearly consistent ..." and "must demonstrate that ... it is clearly consistent ...".
BOILERPLATE = re.compile(r"affirmative finding|could not make|unable to find|burden|persuasion|\bprov(?:e|es|ing)\b"
                         r"|demonstrat", re.I)
# A grant phrase inside a negated finding is a denial's reasoning, not a grant: "... precludes
# a finding that it is clearly consistent ... to grant", "failed to establish that it is ...".
# Checked for the grant phrase only: "has not mitigated ... it is not clearly consistent" is a denial.
NEGATED_GRANT = re.compile(r"preclud|\bfail(?:ed|s|ure)?\b|\b(?:has|have|had|did|does)\s+not\b|\bcannot\b", re.I)
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
# "the Board affirms the Administrative Judge's decision" (1990s orders).
APPEAL_BOARD_VERB = re.compile(r"\bthe\s+Board\s+(affirms|reverses|remands)\b", re.I)
BOARD_VERB = {"affirms": "affirmed", "reverses": "reversed", "remands": "remanded"}
# "Department Counsel's appeal from that favorable decision" states the direction itself.
APPEAL_FROM = re.compile(r"\bappeal\s+from\s+(?:that|the|an?)\s+(favorable|unfavorable|adverse)\s+decision\b", re.I)
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


OPPOSITE = {"approved": "denied", "denied": "approved"}
REVIEWED_OUTCOME = {"adverse": "denied", "favorable": "approved"}


def appeal_ruling(text: str) -> dict[str, Any]:
    """What an Appeal Board decision did and to what, read from its text.

    Returns disposition (affirmed/reversed/remanded), reviewed_outcome (what the
    decision under review had decided: approved/denied, or None when the text does
    not say), appealed_by, outcome (where the clearance ends up; remanded when sent
    back), evidence, and problem when the text does not settle it. Every candidate
    reading is collected; disagreement is a problem, not a choice.
    """
    flat = _flat(text)
    readings: dict[tuple[str, str | None], str] = {}
    for match in APPEAL_EXPLICIT.finditer(flat):
        kind = match.group(1).lower()
        kind = "adverse" if kind == "unfavorable" else kind
        readings.setdefault((match.group(2).lower(), kind), match.group(0))
    for match in APPEAL_DIRECTED.finditer(flat):
        readings.setdefault((match.group(2).lower(), DIRECTION[match.group(1).lower()]), _snippet(flat, match, 160))
    if not readings:
        bare = {match.group(1).lower(): match.group(0) for match in APPEAL_BARE.finditer(flat)}
        for match in APPEAL_BOARD_VERB.finditer(flat):
            bare.setdefault(BOARD_VERB[match.group(1).lower()], match.group(0))
        if len(bare) == 1:
            (verb, said), = bare.items()
            stated = {"adverse" if m.group(1).lower() == "unfavorable" else m.group(1).lower()
                      for m in APPEAL_FROM.finditer(flat)}
            applicant, government = bool(APPELLANT_APPLICANT.search(flat)), bool(APPELLANT_GOVERNMENT.search(flat))
            if len(stated) == 1:
                kind = stated.pop()
                readings[(verb, kind)] = f"'{said}' on an appeal from a {kind} decision"
            elif applicant != government:
                kind = "adverse" if applicant else "favorable"
                readings[(verb, kind)] = f"'{said}' on an appeal by {'Applicant' if applicant else 'Department Counsel'}"
            elif verb == "remanded":
                readings[(verb, None)] = said
    dispositions = {verb for verb, _ in readings}
    kinds = {kind for _, kind in readings if kind}
    if not readings:
        return {"problem": "no order states what the Board did"}
    if len(dispositions) > 1 or len(kinds) > 1:
        return {"problem": "conflicting order statements: " + "; ".join(f"{v}/{k} ('{e[:60]}')"
                                                                         for (v, k), e in sorted(readings.items(), key=str))}
    disposition, kind = dispositions.pop(), (kinds.pop() if kinds else None)
    reviewed = REVIEWED_OUTCOME.get(kind) if kind else None
    applicant, government = bool(APPELLANT_APPLICANT.search(flat)), bool(APPELLANT_GOVERNMENT.search(flat))
    appealed_by = ("Applicant" if applicant else "Department Counsel") if applicant != government else \
        {"adverse": "Applicant", "favorable": "Department Counsel"}.get(kind or "")
    effect = "remanded" if disposition == "remanded" else (reviewed if disposition == "affirmed" else OPPOSITE.get(reviewed or ""))
    if effect is None:
        return {"problem": f"the Board {disposition} a decision whose outcome the text does not state"}
    return {"disposition": disposition, "reviewed_outcome": reviewed, "appealed_by": appealed_by,
            "outcome": effect, "evidence": next(iter(readings.values()))[:160]}


def _statements(region: str) -> dict[str, str]:
    """Outcome statements in a region, skipping boilerplate sentences."""
    region = _flat(region)
    found: dict[str, str] = {}
    for pattern, value in HEARING_OUTCOMES:
        for match in pattern.finditer(region):
            sentence = region[region.rfind(". ", 0, match.start()) + 1:match.start()]
            if BOILERPLATE.search(sentence) or (value == "approved" and NEGATED_GRANT.search(sentence)):
                continue
            found.setdefault(value or WORD_OUTCOME[match.group(1).lower()], match.group(0))
    return found


def _hearing_outcome(text: str) -> dict[str, str]:
    headings = list(CONCLUSION_HEADING.finditer(text))
    return _statements(text[headings[-1].start():] if headings else text[-3000:])


# The opening summary ends where the case history begins; without that heading there is
# no summary distinct from the conclusion, so none is read.
CASE_HISTORY = re.compile(r"^\s*(?:Statement of the Case|History of the Case|Procedural History|Findings of Fact)\s*$",
                          re.M | re.I)
FORMAL_FINDINGS_HEADING = re.compile(r"^\s*Formal Findings\s*$", re.M | re.I)
FINDING_DIRECTION = re.compile(r"\b(for|against)\s+(?:the\s+)?applicant\b", re.I)


def _summary_outcome(text: str) -> dict[str, str]:
    history = CASE_HISTORY.search(text[:20000])
    return _statements(text[:history.start()]) if history else {}


def _findings_outcome(text: str) -> str | None:
    """Denied if any formal finding is against Applicant; approved if all are for; else None."""
    headings = list(FORMAL_FINDINGS_HEADING.finditer(text))
    if not headings:
        return None
    start = headings[-1].end()
    conclusion = CONCLUSION_HEADING.search(text, start)
    section = text[start:conclusion.start() if conclusion else start + 6000]
    section = re.sub(r"\bfor\s+or\s+against\s+(?:the\s+)?applicant\b", " ", section, flags=re.I)  # the section's own preamble
    directions = {m.group(1).lower() for m in FINDING_DIRECTION.finditer(section)}
    if not directions:
        return None
    return "denied" if "against" in directions else "approved"


def hearing_outcome(text: str) -> tuple[str | None, str]:
    """The conclusion, cross-checked against the opening summary and the formal findings.

    A conclusion that one of the others contradicts is a problem, not a choice. A missing
    or self-contradictory conclusion is settled only when the summary and the findings
    both exist and agree (a judge's slip such as "clearly consistent ... to grant ...
    Eligibility ... is denied" under all-For findings and a "granted" summary)."""
    conclusion, summary, findings = _hearing_outcome(text), _summary_outcome(text), _findings_outcome(text)
    said = next(iter(summary)) if len(summary) == 1 else None
    if len(conclusion) == 1:
        (value, evidence), = conclusion.items()
        against = [f"opening summary says {k} ('{v[:60]}')" for k, v in summary.items() if k != value]
        if findings and findings != value:
            against.append(f"formal findings are {'all for' if findings == 'approved' else 'partly against'} Applicant")
        if against:
            return None, f"conclusion says {value} ('{evidence[:60]}') but " + "; ".join(against)
        return value, evidence[:160]
    if said and findings == said:
        state = "states no outcome" if not conclusion else "contradicts itself (" + "; ".join(
            f"{k} ('{v[:50]}')" for k, v in sorted(conclusion.items())) + ")"
        return said, f"conclusion {state}; opening summary ('{summary[said][:60]}') and formal findings agree"
    if not conclusion:
        return None, "no conclusion or order states the outcome"
    return None, "conflicting outcome statements: " + "; ".join(f"{k} ('{v[:80]}')" for k, v in sorted(conclusion.items()))


def outcome(text: str, level: str) -> tuple[str | None, str]:
    """(outcome, evidence) or (None, problem). Ambiguity is a problem, not a guess."""
    if level.startswith("a"):
        ruling = appeal_ruling(text)
        return (ruling["outcome"], ruling["evidence"]) if "outcome" in ruling else (None, ruling["problem"])
    return hearing_outcome(text)


# The published names of each guideline across the 1997, 2006 and 2017 Adjudicative
# Guidelines. KEYWORD lines use whichever name was current, and older decisions use the
# 1997 names ("Security Violations", "Emotional, Mental, and Personality Disorders").
GUIDELINE_NAMES = {
    "A": ("allegiance to the united states",), "B": ("foreign influence",), "C": ("foreign preference",),
    "D": ("sexual behavior",), "E": ("personal conduct",), "F": ("financial considerations",),
    "G": ("alcohol consumption",), "H": ("drug involvement", "substance misuse"),
    "I": ("psychological conditions", "emotional, mental, and personality disorders",
          "emotional, mental and personality disorders"),
    "J": ("criminal conduct",), "K": ("handling protected information", "security violations"),
    "L": ("outside activities",),
    "M": ("use of information technology", "misuse of information technology"),
}
# A segment's first word names one guideline only when no other guideline name starts with
# it ("Financial" is F; "Foreign" could be B or C). "Use" and "Security" are too common.
FIRST_WORD = {"allegiance": "A", "sexual": "D", "personal": "E", "financial": "F", "alcohol": "G",
              "drug": "H", "substance": "H", "psychological": "I", "emotional": "I", "criminal": "J",
              "handling": "K", "outside": "L", "misuse": "M"}


def _keyword_codes(keywords: str, guidelines: dict[str, Any]) -> tuple[set[str], list[str]]:
    """Codes named by a KEYWORD line, and the segments that name no guideline."""
    codes: set[str] = set()
    unmapped = []
    for segment in re.split(r";", keywords):
        lowered = re.sub(r"\s+", " ", segment).strip().lower()
        if not lowered:
            continue
        found = set(GUIDELINE_LETTER.findall(segment))
        for code, item in guidelines.items():
            names = [item.get("label", ""), *item["aliases"], *GUIDELINE_NAMES.get(code, ())]
            if any(name and re.search(r"\b" + re.escape(name.lower()) + r"\b", lowered) for name in names):
                found.add(code)
        first = FIRST_WORD.get(lowered.split(" ")[0].strip(",."))
        if not found and first in guidelines:
            found.add(first)
        codes |= found
        if not found:
            unmapped.append(segment.strip())
    return codes & set(guidelines), unmapped


def topics(text: str, taxonomy: dict[str, Any]) -> tuple[list[str], str]:
    """KEYWORD line first; then formal findings; then the guidelines the SOR alleged.

    A KEYWORD line is trusted alone only when every segment names a guideline. When a
    segment names none, the line may be missing a guideline, so the formal findings (or
    else the SOR) are added to it rather than silently dropping a topic."""
    guidelines = validate_taxonomy(taxonomy)
    line = KEYWORD.search(text[:20000])
    partial: set[str] = set()
    partial_basis = ""
    if line:
        keywords = line.group(1)
        codes, unmapped = _keyword_codes(keywords, guidelines)
        if codes and not unmapped:
            return sorted(codes), f"KEYWORD line '{keywords.strip()[:120]}'"
        if codes:
            partial = codes
            partial_basis = (f"KEYWORD line '{keywords.strip()[:80]}' (segments naming no guideline: "
                             f"{'; '.join(u[:30] for u in unmapped[:3])}) plus ")
    findings = sorted(set(code.upper() for code in FORMAL_FINDING.findall(text)) | set(FORMAL_FINDING_COLUMN.findall(text)))
    if findings:
        return sorted(partial | set(findings)), partial_basis + "formal findings for " + ", ".join(f"Guideline {code}" for code in findings)
    # The Statement of the Case names the guidelines the SOR alleged; older decisions name
    # them later ("with regard to criteria H, E and J").
    for region, basis in ((text[:8000], "guidelines alleged in the Statement of the Case"),
                          (text, "guidelines the decision applies")):
        alleged: set[str] = set()
        for match in SOR_GUIDELINES.finditer(_flat(region)):
            alleged.add(match.group(1))
            alleged.update(re.findall(r"\b([A-M])\b", match.group(2)))
        alleged &= set(guidelines)
        if alleged:
            return sorted(partial | alleged), partial_basis + basis
    if partial:
        return sorted(partial), partial_basis.removesuffix(" plus ") + "; no formal findings or SOR guidelines to complete it"
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


def held_cases(library: Path) -> tuple[dict[str, str | None], set[str], set[str]]:
    """Case keys the library holds (with decision dates where recorded), document IDs and paths."""
    cases: dict[str, str | None] = {}
    ids, paths = set(), set()
    if (library / DOHA_MANIFEST).is_file():
        for row in _rows(library / DOHA_MANIFEST):
            cases[str(row.get("case_stem", "")).split("_")[0].lower()] = row.get("decision_date")
    for row in _rows(library / DOCUMENTS):
        ids.add(row["document_id"])
        for key in ("human_source_path", "robot_text_path"):
            if row.get(key):
                paths.add(str(row[key]).replace("\\", "/").casefold())
    return cases, ids, paths


LEVEL = re.compile(r"^(\d{2}-\d{4,6})\.([ha])(\d)$")


def _related(case_id: str, family: str, known: dict[str, tuple[str | None, str]]) -> list[tuple[str, str | None, str, int]]:
    """Known decisions of one case and family: (key, date, status, number)."""
    found = []
    for key, (decided, status) in known.items():
        match = LEVEL.match(key)
        if match and match.group(1) == case_id and match.group(2) == family:
            found.append((key, decided, status, int(match.group(3))))
    return found


def reviewed_decision(case_id: str, level: str, decided: str, known: dict[str, tuple[str | None, str]]) -> dict[str, Any]:
    """The hearing decision an appeal reviewed: the latest one dated before the appeal;
    else the case's only hearing decision; else the one with the appeal's number."""
    hearings = _related(case_id, "h", known)
    dated = [h for h in hearings if h[1] and h[1] < decided]
    if dated:
        key, date_, status, _ = max(dated, key=lambda h: (h[1], h[3]))
        return {"case_key": key, "decision_date": date_, "status": status,
                "basis": "latest hearing decision of the case dated before the appeal"}
    if len(hearings) == 1:
        key, date_, status, _ = hearings[0]
        return {"case_key": key, "decision_date": date_, "status": status,
                "basis": "the only hearing decision of the case that DOHA lists or the library holds"}
    same = [h for h in hearings if h[3] == int(level[1:])]
    if same:
        key, date_, status, _ = same[0]
        return {"case_key": key, "decision_date": date_, "status": status,
                "basis": "hearing decision with the appeal's number; the case has several and their dates are not all known"}
    return {"case_key": None, "decision_date": None, "status": "not identified",
            "basis": "no hearing decision of this case is listed by DOHA or held by the library"}


def remanded_from(case_id: str, level: str, decided: str, known: dict[str, tuple[str | None, str]]) -> dict[str, Any] | None:
    """For a hearing decision issued on remand, the appeal that sent the case back."""
    appeals = _related(case_id, "a", known)
    dated = [a for a in appeals if a[1] and a[1] < decided]
    if dated:
        key, date_, status, _ = max(dated, key=lambda a: (a[1], a[3]))
        return {"case_key": key, "decision_date": date_, "status": status,
                "basis": "latest appeal decision of the case dated before this decision"}
    earlier = [a for a in appeals if a[3] == int(level[1:]) - 1]
    if earlier:
        key, date_, status, _ = earlier[0]
        return {"case_key": key, "decision_date": date_, "status": status,
                "basis": "appeal numbered one below this hearing decision"}
    return {"case_key": None, "decision_date": None, "status": "not identified",
            "basis": "the decision says it follows a remand; no appeal of this case is listed or held"}


REMAND_TEXT = re.compile(r"\bremand(?:ed)?\b", re.I)


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
    # Every decision this plan can point at, with what is known of it.
    known: dict[str, tuple[str | None, str]] = {key: (None, "listed by DOHA, not acquired") for key in listings}
    packages = {}
    loaded, unreadable = load_packages(run_dir)
    for path, package in loaded:
        packages[Path(package["source_filename"]).stem.lower()] = (path, package)
    known.update({key: (None, "acquired, not in this plan") for key in packages})
    known.update({key: (decided, "held by the library") for key, decided in held.items()})
    links: list[tuple[dict[str, Any], str, str, str, str]] = []
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
        ruling = appeal_ruling(text) if level.startswith("a") else {}
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
        if ruling:
            outcome_basis = (f"the Board {ruling['disposition']} the decision under review "
                             f"({ruling['reviewed_outcome'] or 'outcome not stated'}); {ruling['evidence']}")
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
                    **({"appeal_disposition": ruling["disposition"], "appealed_by": ruling["appealed_by"],
                        "reviewed_decision": {"outcome": ruling["reviewed_outcome"]}} if ruling else {}),
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
        if ruling:
            counts[f"{group_name}/appeal/{ruling['disposition']} (clearance {result})"] += 1
        else:
            counts[f"{group_name}/hearing/{'granted' if result == 'approved' else result}"] += 1
        review = items[-1]["record"]["doha_review"]
        on_remand = level.startswith("h") and (int(level[1:]) > 1 or bool(REMAND_TEXT.search(text)))
        links.append((review, key, case_id, level, decided if not on_remand or level.startswith("a") else "remand"))
        known[key] = (decided, "in this plan")
        counts["answer_eligible"] += eligible
    # Links are resolved once every decision in the plan is known, so an appeal can
    # point at a hearing decision planned after it.
    for review, key, case_id, level, marker in links:
        decided = review["decision_date"]
        if level.startswith("a"):
            review["reviewed_decision"] = {**reviewed_decision(case_id, level, decided, known), **review["reviewed_decision"]}
        elif marker == "remand":
            review["decided_on_remand_from"] = remanded_from(case_id, level, decided, known)
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
