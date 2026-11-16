"""A Librarian quarantine package for a Voice of Industry issue becomes a reviewed intake plan.

Reads the package and, read-only, the library manifest. Writes only the new plan folder:
a copy of the package and its source, the robot text, a parity report and `plan.json`
for `build-candidate --intake-plan`. Nothing here writes the library; the only write
path stays build-candidate, validate, evaluate, publish.

Reproducible by construction: the robot text is a function of the source bytes alone.
The extractor is pinned to one pypdf version (another version wraps table cells
differently and so changes the hash of unchanged content), and the header carries no
generation date and no retrieval detail.

The issue period is read from the issue's own masthead, never from a file name, and is
cross-checked against the Librarian's `publisher_claim` and a `confirm-period` receipt
when one is supplied. Any disagreement stops the command.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from .common import iter_jsonl, norm, read_json, sha256_file, utc_now, write_json
from .naming import MONTHS, check_collection_name
from .release_contract import bounded_path

# The one extractor version whose output this command accepts. Changing it changes the
# bytes of every text extracted afterwards: change it deliberately, with the test.
PYPDF_VERSION = "6.0.0"
EXTRACTOR = f"pypdf {PYPDF_VERSION} PageObject.extract_text(), default mode"
PLAN_NAME = "plan.json"
REPORT_NAME = "extraction-report.json"

COLLECTION = "voi"
DOMAIN = "industrial_security"
AUTHORITY_TIER = 7
FOLDER = "INDUSTRIAL_SECURITY/VOICE_OF_INDUSTRY_VOI"
# Each page's words must be found by a second, independent extractor, and the reverse.
MIN_PAGE_AGREEMENT = 0.90
MASTHEAD_LINES = 25

_MONTH_NAMES = MONTHS.split("|")
_PERIOD_LINE = re.compile(rf"(?:\d{{1,2}} )?({MONTHS}) (20\d\d)")
_PERIOD_ANYWHERE = re.compile(rf"\b({MONTHS})\s+(20\d\d)\b")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")  # form feed included: it is the page locator


def _pypdf():
    try:
        import pypdf
    except ImportError as exc:
        raise RuntimeError(f"voi-intake-plan needs pypdf=={PYPDF_VERSION} in {sys.executable}: {exc}") from exc
    if pypdf.__version__ != PYPDF_VERSION:
        raise RuntimeError(
            f"voi-intake-plan is pinned to pypdf {PYPDF_VERSION} but {sys.executable} has {pypdf.__version__}. "
            "Another version wraps lines differently and would change the robot text hash for unchanged "
            f"content. Run with an interpreter that has pypdf=={PYPDF_VERSION}; nothing was written.")
    return pypdf


def normalise_page(text: str) -> str:
    """LF line ends, no control characters (a stray form feed would fake a page break), no trailing blank."""
    return _CONTROL.sub("", text.replace("\r\n", "\n").replace("\r", "\n")).rstrip()


def extract_pages(pdf: Path) -> tuple[list[str], dict[str, str]]:
    """Each page's embedded text from the pinned extractor, normalised; plus the PDF's own metadata."""
    reader = _pypdf().PdfReader(str(pdf))
    pages = [normalise_page(page.extract_text() or "") for page in reader.pages]
    return pages, {str(key): str(value) for key, value in (reader.metadata or {}).items()}


def masthead_period(first_page: str) -> dict[str, Any]:
    """The month and year the issue states at the top of page 1, with where it says so."""
    lines = first_page.split("\n")
    end = next((i for i, line in enumerate(lines) if line.strip().upper().startswith("TABLE OF CONTENTS")), len(lines))
    found = []
    for number, line in enumerate(lines[:min(end, MASTHEAD_LINES)], 1):
        match = _PERIOD_LINE.fullmatch(line.strip())
        if match:
            found.append((match.group(1), int(match.group(2)), number, line.strip()))
    periods = {(month, year) for month, year, _, _ in found}
    if not periods:
        raise ValueError("page 1 masthead states no issue month and year; the period is never taken from the file "
                         "name, so this issue needs a reviewer's hand-written plan (docs/INTAKE-AND-EVENTS.md)")
    if len(periods) > 1:
        raise ValueError(f"page 1 masthead states more than one period: {sorted(periods)}")
    if "voice of industry" not in " ".join(first_page.split()).casefold():
        raise ValueError("page 1 does not identify the document as the Voice of Industry")
    if any(line.strip().upper() in ("SPECIAL BULLETIN", "BULLETIN") for line in lines[:min(end, MASTHEAD_LINES)]):
        raise ValueError("this is a bulletin, not the monthly newsletter; write its plan by hand "
                         "(docs/INTAKE-AND-EVENTS.md)")
    month, year, number, line = found[0]
    return {"month": month, "year": year, "period": f"{year}-{_MONTH_NAMES.index(month) + 1:02d}",
            "locator": f"SOURCE PAGE 1, line {number}", "text": line}


def _claimed_period(value: object) -> str | None:
    match = _PERIOD_ANYWHERE.search(str(value or ""))
    return f"{match.group(2)}-{_MONTH_NAMES.index(match.group(1)) + 1:02d}" if match else None


def check_confirm_period(path: Path, period: str, source_sha256: str) -> dict[str, Any]:
    """A Librarian confirm-period marker (or the receipt it was made from) must agree, or the command stops."""
    data = read_json(path)
    evidence = data.get("evidence") if isinstance(data.get("evidence"), dict) else data
    stated = evidence.get("source_period") or data.get("period")
    if data.get("period") not in (None, stated):
        raise ValueError(f"confirm-period receipt is inconsistent: period {data.get('period')}, source_period {stated}")
    if evidence.get("issue_period_verified") is not True:
        raise ValueError("confirm-period receipt does not record a verified issue period")
    if stated != period:
        raise ValueError(f"issue period mismatch: the masthead says {period}, the confirm-period receipt says {stated}")
    if evidence.get("source_sha256") != source_sha256:
        raise ValueError("confirm-period receipt is for different source bytes than this package")
    return {"path": str(path), "sha256": sha256_file(path), "period": stated,
            "reviewed_by": evidence.get("reviewed_by"), "issue_locator": evidence.get("issue_locator")}


def robot_text(pages: list[str], stem: str, source_sha256: str) -> str:
    """The library's VOI page-locator convention: a form feed, then `===== SOURCE PAGE n =====`."""
    human = f"HUMAN_READABLE_DIRECTORY/{FOLDER}/{stem}.pdf"
    body = ["MACHINE-READABLE TEXT COPY", f"Source PDF: {stem}.pdf", f"Source path: {human}",
            f"Source SHA-256: {source_sha256}",
            f"Method: embedded PDF text extraction using pypdf {PYPDF_VERSION} (pinned); "
            "the same source bytes always give this same text.",
            "Use: search, retrieval, and analysis aid. Consult the source PDF for authoritative visual "
            "formatting and any extraction ambiguity.",
            f"Source page count: {len(pages)}",
            f"Authority: Tier {AUTHORITY_TIER} DCSA newsletter; operational guidance/context, never independently authoritative.",
            ""]
    for number, text in enumerate(pages, 1):
        body.extend(["\f", f"===== SOURCE PAGE {number} =====", "", text, ""])
    return "\n".join(body).rstrip() + "\n"


def _words(text: str) -> Counter[str]:
    # Letters and digits only, so dot leaders and typographic quotes do not count as disagreement.
    return Counter(re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKC", text).casefold()))


def pdftotext_pages(binary: str | None = None) -> Callable[[Path], tuple[list[str], str]]:
    """An independent extractor for the parity check. Its output never enters the robot text."""
    tool = binary or shutil.which("pdftotext")
    if not tool:
        raise RuntimeError("the parity check needs an independent extractor: install pdftotext or pass --pdftotext <path>")
    version = subprocess.run([tool, "-v"], capture_output=True, text=True, timeout=60)
    banner = ((version.stdout + version.stderr).strip().splitlines() or ["pdftotext (no version banner)"])[0]

    def extract(pdf: Path) -> tuple[list[str], str]:
        done = subprocess.run([tool, "-enc", "UTF-8", str(pdf), "-"], capture_output=True, timeout=300, check=True)
        pages = done.stdout.decode("utf-8", "replace").split("\f")
        return (pages[:-1] if pages and not pages[-1].strip() else pages), banner
    return extract


def parity(pages: list[str], text: str, other_pages: list[str]) -> dict[str, Any]:
    sections = re.split(r"\f\n===== SOURCE PAGE \d+ =====\n\n", text)[1:]
    sections_match = len(sections) == len(pages) and all(a.strip() == b.strip() for a, b in zip(pages, sections))
    rows = []
    if len(other_pages) == len(pages):
        for number, (mine, theirs) in enumerate(zip(pages, other_pages), 1):
            a, b = _words(mine), _words(theirs)
            common = sum((a & b).values())
            rows.append({"page": number, "words": sum(a.values()), "independent_words": sum(b.values()), "common": common,
                         "share_of_independent_words_present": round(common / max(1, sum(b.values())), 4),
                         "share_of_words_confirmed": round(common / max(1, sum(a.values())), 4)})
    weak = [row["page"] for row in rows if min(row["share_of_independent_words_present"],
                                               row["share_of_words_confirmed"]) < MIN_PAGE_AGREEMENT]
    return {"sections_match_pages": sections_match, "independent_page_count": len(other_pages),
            "page_counts_agree": len(other_pages) == len(pages), "pages": rows,
            "minimum_page_agreement_required": MIN_PAGE_AGREEMENT, "pages_below_minimum": weak,
            "passed": sections_match and len(other_pages) == len(pages) and not weak}


def build_voi_plan(library_root: Path, package_path: Path, out: Path,
                   independent: Callable[[Path], tuple[list[str], str]],
                   confirm_period: Path | None = None, reviewed_by: str | None = None) -> dict[str, Any]:
    library_root, package_path, out = library_root.resolve(), package_path.resolve(), out.resolve()
    if not package_path.name.endswith(".intake.json"):
        raise ValueError("--package is the Librarian's <source file>.intake.json")
    if out == library_root or out.is_relative_to(library_root):
        raise ValueError("the plan folder may not be inside the library; this command never writes the library")
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise FileExistsError(f"plan folder already has content; choose a new one: {out}")

    package = read_json(package_path)
    if package.get("approval_state") != "quarantined_unreviewed":
        raise ValueError("expected quarantined Librarian package")
    for field in ("requested_source_uri", "resolved_source_uri"):
        if urlparse(str(package.get(field, ""))).scheme != "https":
            raise ValueError(f"missing HTTPS provenance: {field}")
    if not package.get("retrieved_at") or not package.get("mime_type"):
        raise ValueError("missing retrieval provenance")
    source = bounded_path(package_path.parent, package["source_filename"], "")
    source_sha256 = sha256_file(source)
    if source_sha256 != package["source_sha256"] or source.stat().st_size != package["source_bytes"]:
        raise ValueError("quarantined source hash/size mismatch")

    pages, metadata = extract_pages(source)
    if not pages:
        raise ValueError("the source has no pages")
    empty = [number for number, text in enumerate(pages, 1) if not text.strip()]
    if empty:
        raise ValueError(f"pages with no embedded text need OCR and a reviewer's plan: {empty}")
    masthead = masthead_period(pages[0])
    period = masthead["period"]

    evidence = [f"masthead ({masthead['locator']}: '{masthead['text']}')"]
    claim = package.get("publisher_claim")
    claimed = _claimed_period(claim)
    if claimed and claimed != period:
        raise ValueError(f"issue period mismatch: the masthead says {period}, the Librarian's publisher_claim says "
                         f"'{claim}' ({claimed})")
    if claimed:
        evidence.append(f"Librarian publisher_claim '{claim}' agrees")
    else:
        evidence.append("no usable Librarian publisher_claim" if not claim else
                        f"Librarian publisher_claim '{claim}' states no month and year and was not used")
    receipt = None
    if confirm_period is not None:
        receipt = check_confirm_period(confirm_period.resolve(), period, source_sha256)
        evidence.append(f"Librarian confirm-period receipt agrees ({receipt['path']}, SHA-256 {receipt['sha256']})")
    else:
        evidence.append("no Librarian confirm-period receipt was supplied")

    stem = f"Voice of Industry - {masthead['month']} {masthead['year']} Newsletter"
    record = {
        "document_id": f"dcsa-voi-{period}-voi", "title": stem, "collection_id": COLLECTION, "domain": DOMAIN,
        "authority_tier": AUTHORITY_TIER, "current_status": "current_or_verify",
        "human_source_path": f"HUMAN_READABLE_DIRECTORY/{FOLDER}/{stem}.pdf",
        "robot_text_path": f"ROBOT_READABLE_DIRECTORY/TEXT/{FOLDER}/{stem}.txt",
    }
    check_collection_name(record)
    entry = read_json(library_root / "START_HERE_FOR_ROBOTS.json")
    held = [row for _, row in iter_jsonl(bounded_path(library_root, entry["documents"], "ROBOT_READABLE_DIRECTORY/MANIFESTS/"))]
    used = {norm(row.get(key)).casefold() for row in held for key in ("human_source_path", "robot_text_path")}
    if any(str(row.get("document_id")) == record["document_id"] for row in held):
        raise ValueError(f"the library already holds {record['document_id']}; intake adds new issues only")
    for key in ("human_source_path", "robot_text_path"):
        if record[key].casefold() in used or (library_root / record[key]).exists():
            raise ValueError(f"the library already has a file at {record[key]}")
    siblings = [row for row in held if row.get("collection_id") == COLLECTION]
    if not siblings:
        raise ValueError("the library holds no voi collection to add this issue to")

    text = robot_text(pages, stem, source_sha256)
    other_pages, banner = independent(source)
    check = parity(pages, text, other_pages)
    report = {
        "schema_version": "1.0", "source": source.name, "source_sha256": source_sha256, "source_bytes": source.stat().st_size,
        "extractor": EXTRACTOR, "python": sys.version.split()[0], "pages": len(pages),
        "page_characters": [len(page) for page in pages], "masthead": masthead, "period_evidence": evidence,
        "confirm_period_receipt": receipt, "pdf_metadata": metadata, "independent_extractor": banner,
        "parity": check, "robot_file": f"{stem}.txt",
    }
    out.mkdir(parents=True, exist_ok=True)
    robot = out / f"{stem}.txt"
    robot.write_bytes(text.encode("utf-8"))
    report.update(robot_sha256=sha256_file(robot), robot_bytes=robot.stat().st_size, generated_utc=utc_now())
    write_json(out / REPORT_NAME, report)
    if not check["passed"]:
        raise ValueError(f"extraction parity failed (pages below {MIN_PAGE_AGREEMENT:.0%} agreement: "
                         f"{check['pages_below_minimum']}; page counts agree: {check['page_counts_agree']}); "
                         f"no plan was written. See {out / REPORT_NAME}")

    shutil.copyfile(package_path, out / package_path.name)
    shutil.copyfile(source, out / source.name)
    if sha256_file(out / source.name) != source_sha256:
        raise ValueError("the staged copy of the source does not match the package")
    shares = [min(row["share_of_independent_words_present"], row["share_of_words_confirmed"]) for row in check["pages"]]
    reviewer = reviewed_by or "dcsa-archivist voi-intake-plan (automated evidence checks)"
    review = {
        "reviewed_by": reviewer, "reviewed_utc": utc_now(),
        "identity": f"Page 1 of the quarantined PDF identifies the Voice of Industry and states the issue period "
                    f"'{masthead['text']}' at {masthead['locator']}. PDF metadata title: "
                    f"{metadata.get('/Title', 'none')!r}; created {metadata.get('/CreationDate', 'not stated')!r}.",
        "provenance": f"Librarian package binds {package['resolved_source_uri']} (requested "
                      f"{package['requested_source_uri']}), retrieved {package['retrieved_at']}, {package['mime_type']}. "
                      f"The quarantined bytes were rehashed: SHA-256 {source_sha256}, {source.stat().st_size} bytes, "
                      "equal to the package. This command did not open the publisher's page.",
        "extraction": f"{EXTRACTOR} on all {len(pages)} pages; characters per page {report['page_characters']}; no page "
                      f"without embedded text. Locators SOURCE PAGE 1-{len(pages)}. Robot text SHA-256 "
                      f"{report['robot_sha256']}, reproducible from the source bytes.",
        "parity": f"Every SOURCE PAGE section equals its page's extraction ({len(pages)}/{len(pages)}). An independent "
                  f"extractor ({banner}) found the same page count and agrees on {min(shares):.1%} to {max(shares):.1%} "
                  f"of words per page, both directions (minimum required {MIN_PAGE_AGREEMENT:.0%}). Automated checks "
                  "only: tables and figures were not read against the rendered pages.",
        "taxonomy": f"Collection {COLLECTION}, domain {DOMAIN}, authority tier {AUTHORITY_TIER}, as the {len(siblings)} "
                    f"voi records the library holds. Name follows the enforced pattern 'Voice of Industry - <Month> "
                    "<YYYY> Newsletter' (src/dcsa_custodian/naming.py) with month and year from the masthead, not from "
                    "the download's file name. The document ID and both paths are unused in the library.",
        "lifecycle": f"Issue period {period} rests on: {'; '.join(evidence)}. Recorded current_or_verify; no binding "
                     "authority, rescission or supersession is inferred. Substantive relationships are Guidance Watch's.",
    }
    plan = {"schema_version": "1.0", "items": [{
        "package": package_path.name, "robot_file": robot.name, "robot_sha256": report["robot_sha256"],
        "record": record, "review": review}]}
    write_json(out / PLAN_NAME, plan)
    return {"status": "plan_ready", "plan": str(out / PLAN_NAME), "report": str(out / REPORT_NAME),
            "document_id": record["document_id"], "title": stem, "period": period, "period_evidence": evidence,
            "robot_file": str(robot), "robot_sha256": report["robot_sha256"], "robot_bytes": report["robot_bytes"],
            "pages": len(pages), "extractor": EXTRACTOR,
            "next": f'build-candidate --release-id <id> --deep --intake-plan "{out / PLAN_NAME}"'}
