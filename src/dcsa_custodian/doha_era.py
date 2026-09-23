"""Assign each DOHA decision to its SEAD 4 era from the date it was issued.

SEAD 4 took effect on 8 June 2017, and DOHA applied it to decisions issued on or
after that date. The era therefore follows the decision date, never the case
number: a case docketed in 2016 and decided in 2018 is post-SEAD 4.

The date comes from the decision text: the ``DATE:`` header, or the date line
between "Appearances" and "Decision". That date is checked against the record
itself. A decision cannot precede its own docket year, the day the case was
assigned, the hearing, receipt of the transcript or the close of the record.
When the stated date contradicts those events it is not trusted; the era is then
taken from the latest such event only when that alone places the decision after
the cutoff, and is otherwise left undetermined for review. Filenames, folders
and case numbers are never read as an era.

Portable stdlib code. Reads robot text only.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

SEAD4_EFFECTIVE = date(2017, 6, 8)
ERA_RULE = ("post_sead4 when the decision was issued on or after 2017-06-08, the SEAD 4 effective date; "
            "pre_sead4 when issued before it; undetermined when the issue date cannot be established")
ERAS = {"post_sead4": "POST_SEAD_4", "pre_sead4": "PRE_SEAD_4", "undetermined": "UNDETERMINED"}
GROUP_ERAS = {group: era for era, group in ERAS.items()}

_MONTHS = {name: number for number, name in enumerate(
    "january february march april may june july august september october november december".split(), 1)}
_MONTH = r"(January|February|March|April|May|June|July|August|September|October|November|December)"
_LONG = _MONTH + r"\s+(\d{1,2})\s*,?\s*(\d{4})"
_HEADER_NUMERIC = re.compile(r"^\s*DATE:\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$", re.M)
_HEADER_LONG = re.compile(r"^\s*DATE:\s*" + _LONG + r"\s*$", re.M | re.I)
_LINE_NUMERIC = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$", re.M)
_LINE_LONG = re.compile(r"^\s*" + _LONG + r"\s*$", re.M | re.I)
_APPEARANCES = re.compile(r"Appearances", re.I)
_DECISION_LINE = re.compile(r"^[\s_]*Decision[\s_]*$", re.M | re.I)
# Events that precede the decision in every case. Each phrase ends where its date begins.
_PROCEDURAL = re.compile(
    r"(?:case\s+was\s+(?:re)?assigned\s+to\s+(?:me|this\s+administrative\s+judge|the\s+undersigned)"
    r"|(?:I|the\s+undersigned)\s+(?:was|were)\s+(?:re)?assigned\s+(?:the\s+case|this\s+case)"
    r"|record\s+(?:was\s+)?closed"
    r"|hearing\s+(?:was\s+)?(?:held|convened|conducted)"
    r"|(?:DOHA\s+)?received\s+the\s+(?:hearing\s+)?transcript(?:\s+of\s+the\s+hearing)?(?:\s*\(Tr\.?\))?"
    r"|transcript(?:\s+of\s+the\s+hearing)?(?:\s*\(Tr\.?\))?\s+was\s+received(?:\s+by\s+DOHA)?)"
    r"\s+on\s+(?:or\s+about\s+)?" + _LONG, re.I)
_HEADER_WINDOW = 20000
_CAPTION_WINDOW = 5000
_PROCEDURAL_WINDOW = 30000
_EARLIEST_PLAUSIBLE = date(1990, 1, 1)


def _date(year: str, month: int | str, day: str) -> date | None:
    try:
        value = date(int(year), int(month), int(day))
    except ValueError:
        return None
    return value if _EARLIEST_PLAUSIBLE <= value <= date.today() else None


def _long(match: re.Match[str], offset: int = 1) -> date | None:
    return _date(match.group(offset + 2), _MONTHS[match.group(offset).lower()], match.group(offset + 1))


def _month(year: str, month: str) -> tuple[date, date] | None:
    """The span of a numeric date whose day is impossible (03/32/2018): the month is still evidence."""
    try:
        first = date(int(year), int(month), 1)
    except ValueError:
        return None
    following = date(first.year + first.month // 12, first.month % 12 + 1, 1)
    return (first, date.fromordinal(following.toordinal() - 1)) if first >= _EARLIEST_PLAUSIBLE else None


def stated_date(text: str) -> tuple[date | None, str]:
    """The issue date the decision states for itself, and where it was found."""
    value, where, _ = _stated(text)
    return value, where


def _stated(text: str) -> tuple[date | None, str, tuple[date, date] | None]:
    head = text[:_HEADER_WINDOW]
    match = _HEADER_NUMERIC.search(head)
    if match:
        return (_date(match.group(3), match.group(1), match.group(2)), "header_date",
                _month(match.group(3), match.group(1)))
    match = _HEADER_LONG.search(head)
    if match:
        return _long(match), "header_date", None
    # The caption's date line sits just above the "Decision" heading, below
    # "Appearances" when the decision has that heading.
    appearances = _APPEARANCES.search(head)
    start = appearances.end() if appearances else 0
    decision = _DECISION_LINE.search(head, start, start + _CAPTION_WINDOW)
    window = head[start:decision.start()] if decision else head[start:start + 1500]
    where = "appearances_date_line" if appearances else "caption_date_line"
    lines = [m for m in (*_LINE_NUMERIC.finditer(window), *_LINE_LONG.finditer(window))]
    if lines:
        match = max(lines, key=lambda m: m.start())
        if match.re is _LINE_NUMERIC:
            return (_date(match.group(3), match.group(1), match.group(2)), where,
                    _month(match.group(3), match.group(1)))
        return _long(match), where, None
    return None, "no_stated_date", None


def procedural_floor(text: str) -> tuple[date | None, str | None]:
    """The latest pre-decision event date in the record, with the phrase naming it."""
    latest: tuple[date | None, str | None] = (None, None)
    for match in _PROCEDURAL.finditer(text[:_PROCEDURAL_WINDOW]):
        value = _long(match, 1)
        if value and (latest[0] is None or value > latest[0]):
            latest = (value, " ".join(match.group(0).split()))
    return latest


def case_year(case_id: str) -> int | None:
    match = re.match(r"(\d{2})-", case_id or "")
    if not match:
        return None
    year = int(match.group(1))
    return year + (2000 if year < 50 else 1900)


def era_for(value: date) -> str:
    return "post_sead4" if value >= SEAD4_EFFECTIVE else "pre_sead4"


def listing_span(title: str) -> tuple[date | None, date | None, str] | None:
    """The issue-date bound implied by the official DOHA listing a decision is posted on.

    A decision cannot be posted before it issues, so the listing year bounds the
    issue date from above: "2016 and Prior" means 2016 at the latest. It is no
    lower bound. DOHA posts late: in this corpus 1,251 decisions with a sound
    date sit on the listing for the year after the one they were issued in.
    """
    match = re.search(r"\b(19|20)(\d{2})\b", title or "", re.I)
    if not match:
        return None
    return None, date(int(match.group(1) + match.group(2)), 12, 31), f"official listing '{title}'"


def classify(text: str, case_id: str, review: dict[str, Any] | None = None,
             listing_title: str | None = None) -> dict[str, Any]:
    """Era, decision date and the basis for both. A reviewed decision takes precedence.

    ``listing_title`` is the title of the official DOHA page the decision is posted
    on, when provenance records one; its year bounds the issue date.
    """
    if review is not None:
        return _reviewed(review)
    stated, where, month = _stated(text)
    floor, floor_event = procedural_floor(text)
    docket = case_year(case_id)
    listing = listing_span(listing_title) if listing_title else None
    lowers = [(floor, f"'{floor_event}'")] if floor else []
    uppers = []
    if docket:
        lowers.append((date(docket, 1, 1), f"the {docket} docket year"))
    if listing:
        if listing[0]:
            lowers.append((listing[0], listing[2]))
        uppers.append((listing[1], listing[2]))
    claimed = stated or (month[0] if month else None)
    conflicts = [f"stated date {(stated or claimed).isoformat()} precedes {event} ({bound.isoformat()})"
                 for bound, event in lowers if claimed and (stated or month[1]) < bound]
    conflicts += [f"stated date {claimed.isoformat()} follows {event} ({bound.isoformat()})"
                  for bound, event in uppers if claimed and claimed > bound]
    if stated and not conflicts:
        return {"sead4_era": era_for(stated), "decision_date": stated.isoformat(),
                "decision_date_basis": where, "era_basis": "decision_date", "date_conflicts": []}
    if month and not conflicts:
        lowers.append((month[0], f"the stated month {month[0]:%Y-%m} (day invalid)"))
        uppers.append((month[1], f"the stated month {month[0]:%Y-%m} (day invalid)"))
    lower = max(lowers, key=lambda item: item[0]) if lowers else None
    upper = min(uppers, key=lambda item: item[0]) if uppers else None
    result = {"decision_date": None,
              "decision_date_basis": "stated_date_contradicted" if conflicts else where if month else "no_stated_date",
              "date_conflicts": conflicts}
    if lower and lower[0] >= SEAD4_EFFECTIVE:
        result.update(sead4_era="post_sead4", era_basis=f"issued no earlier than {lower[1]} ({lower[0].isoformat()})")
    elif upper and upper[0] < SEAD4_EFFECTIVE:
        result.update(sead4_era="pre_sead4", era_basis=f"issued no later than {upper[1]} ({upper[0].isoformat()})")
    else:
        result.update(sead4_era="undetermined", era_basis="issue date not established; needs review")
    return result


def _reviewed(review: dict[str, Any]) -> dict[str, Any]:
    for key in ("reviewed_by", "reviewed_utc", "evidence"):
        if not isinstance(review.get(key), str) or not review[key].strip():
            raise ValueError(f"DOHA era review for {review.get('document_id')} requires {key}")
    decided = review.get("decision_date")
    if decided is not None:
        value = date.fromisoformat(decided)
        era = era_for(value)
        if review.get("sead4_era", era) != era:
            raise ValueError(f"DOHA era review for {review.get('document_id')} contradicts its own decision date")
    else:
        era = review.get("sead4_era")
        if era not in ERAS:
            raise ValueError(f"DOHA era review for {review.get('document_id')} needs a decision_date or sead4_era")
    return {"sead4_era": era, "decision_date": decided, "decision_date_basis": "reviewed" if decided else None,
            "era_basis": f"review by {review['reviewed_by']}: {review['evidence']}", "date_conflicts": []}
