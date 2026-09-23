# HANDOFF — dcsa-archivist

Last updated: 2026-09-22 by Claude

## Current State
2026-09-22: Published `doha-era-and-provenance-20260922` (autonomous after gates:
validate valid/publishable, evaluate 16/16, doctor integrity_healthy,
production_response_ready, 8 verified indexes, doha_era_inconsistencies 0).
Two DOHA defects the Adjudication Atlas converter reported are fixed.

**Era.** The live flag grouped decisions by case number: everything below case
16-02941 was pre-SEAD 4, everything at or above it post. That is the delineation
case the August 2026 split was anchored to (recorded as 16-20941, a
transposition), and its own decision date is 2017-07-31 — the cutoff that split
used. Era now follows the date each decision states for itself, against the real
rule: SEAD 4 took effect 2017-06-08 and DOHA applied it to decisions issued on
or after that date. 1,221 decisions moved pre -> post. The stated date is checked
against the docket year, the case's own procedural events (assignment, hearing,
transcript, record close) and the official listing year, which bounds from above
only — DOHA posts late, and 1,251 sound dates sit on the next year's listing.
27 decisions state a date their own record contradicts; where the bounds still
settle the era it is taken, otherwise the decision is UNDETERMINED and excluded
from default retrieval. 17 remain, all within weeks of the cutoff and listed in
the release report. Four that only the text settles are reviewed decisions with
evidence in decisions/doha_era_reviews.json.

**Provenance.** All 10,658 decisions now record an official DOHA URL:
`source_url` with `source_url_basis` in both DOHA manifests, plus the listing
page, capture time and alternates. 317 are `legacy_download_bytes_identical`
(retained bytes equal a recorded download of that URL); 10,341 are
`official_listing_label` — the official listing publishes that case number and
level at that URL, which is weaker than a byte match and says so. 334 decisions
are posted twice under different FileIds; both URLs are kept and the listing
year is withheld, so a contested year never bounds an era.

Era lives in six stores (both DOHA manifests, both DOHA indexes including the
FTS corpus column, and documents.jsonl). A candidate rewrites all of them from
one classification; validation recomputes every era from the text and refuses a
candidate where any copy disagrees or an era stops following the date, so a
case-number or folder rule cannot come back. Paths did not move: the
PRE_SEAD_4/POST_SEAD_4 folder in a path is storage, not era, and the published
rules file now says so. 93 tests pass.

2026-09-19: Published `release-change-summaries-20260919` (no document changes;
validate ok, evaluate 16/16, doctor healthy). Every publication now writes a compact
per-release change summary to ROBOT_READABLE_DIRECTORY/STATE/RELEASE_CHANGES/ and
binds all of them in the pointer's metadata_sha256; history reaches back to
nist-172-r3-intake-20260911. Question Bot uses them for scoped wiki revalidation.

Published `dd254-canonical-title-20260918` (2026-09-18, autonomous after gates):
validate valid/publishable, evaluate 16/16, doctor integrity_healthy and
production_response_ready, 0 duplicate IDs/groups/tier conflicts, 3 unresolved
currency, 8 verified indexes. Change set: exactly two records. The correctly named
Expired_For_Reference_Only DEC 1999 DD 254 is now canonical (historical_only, 2
historical chunks); the byte-identical FOCI copy is excluded_duplicate with a
reviewed display title. No source bytes, paths or IDs changed.

New metadata decision options (tests cover each): `canonical: true` (reviewed
duplicate-group choice), `title` (reviewed display title), and the `provenance`
disposition (official URL only on reacquired-bytes = retained-bytes). New CLI
`import-provenance --ledger` loads the Librarian's byte-verified ledger.

Roles: Library Coordinator (agents/conductor.md), Evidence Reviewer, Release
Manager, with a cross-process publication lock. New rebuilds route to
dcsa-library-rebuilder; regenerate is legacy. 81 tests pass. All work committed.

## Next
1. 17 DOHA decisions are UNDETERMINED (release report, doha-era-and-provenance-20260922).
   Each needs a reviewed decision or a better extraction; they are excluded from
   default retrieval until then. Their texts state no usable date, or state one
   their own record contradicts, and all sit within weeks of 2017-06-08.
2. 25 DOHA manifest rows point at robot text files that do not exist; their era
   came from the indexed copy in the case index. Separate defect, not fixed here.
3. DOHA era changes deliberately raise no per-document comparison events (the
   change packet tracks source and lifecycle fields, not era). Consumers read
   DOHA_SEAD4_RETRIEVAL_RULES.json and the release report instead. If Question Bot
   should revalidate wiki answers citing a precedent that moved era, that has to be
   decided and built.
4. Guidance Watch and comparison still owe reviews for three release events
   (nist-172-r3-intake-20260911, dd254-dec1999-lifecycle-fix-20260915,
   dd254-canonical-title-20260918); acknowledge only with their hashed receipts.
5. When the Librarian's ledger has verified provenance rows, run import-provenance,
   then build/validate/evaluate/publish. That is how the Rebuilder's 749
   retained-bytes-only records gain official URLs.
6. Continue the shared audit; DOHA implementation is in docs/DOHA-INTAKE.md.

## Open Questions
None open. The DD 254 relabel question (options a/b/c) was resolved on 2026-09-18
with option (c) plus a reviewed canonical choice, at the owner's direction.

## Log
2026-09-22 Claude — Corrected the DOHA SEAD 4 era to follow the decision date and
recorded an official source URL for every decision. The old flag followed case-number
order against the delineation case, which is why 1,221 decisions issued after
2017-06-08 sat in PRE_SEAD_4 and stayed out of default precedent retrieval. Stated
dates are not trusted blindly: 27 contradict their own record, so bounds decide or
the era stays undetermined. The listing year bounds only from above, because DOHA
posts late. Validation recomputes every era from the text, which is what stops the
case-number rule returning under another name.
2026-09-19 Claude — Added published, hash-bound release change summaries (owner-approved
scoped wiki revalidation). Test covers publication, cumulative history and tamper.
2026-09-18 Claude — Resolved the DD 254 relabel and the _canonical_sort gap with
reviewed decisions rather than a heuristic change, so no other duplicate group's
canonical pick moved (verified: 2 records changed). Added provenance decisions so
URLs recovered by byte match can reach the published manifest and the Rebuilder
census. Committed and pushed the Sept 10-17 Codex work first.
2026-09-17 Codex — Implemented the user-approved role split with scoped specialist inputs,
outputs, retry ownership and one coordinator writing the handoff. Kept the existing host
entry path and all gate/receipt formats. Reconciled stale skill approval/intake/naming
instructions. Added per-library OS publication exclusion; tests cover competing processes,
separate libraries, exception recovery, preflight coverage and dry-run corpus preservation.
All 73 tests pass; skill validator (UTF-8 mode), workspace check and diff check pass.
The sibling lock file persists; OS ownership ends on exit. No live release or schedule change.

2026-09-17 Codex — Reviewed conductor, intake contract, enrichment and publication code.
The conductor spans acquisition through Guidance Watch in one session; existing hash-bound
intake plans and release events provide useful role boundaries. Recommend scoped review
and release roles, deterministic build/validation tools, and single-writer publication.
Current publish checks stale baselines but has no enclosing publisher lock. Naming and
intake instructions also need reconciliation. Workspace health check passed; no runtime
tests or production audit performed, and no code/library changes made.

2026-09-16 Codex — Shared directive splitter now supports truthful producer attribution and blocks
noncurrent/ineligible directive section output. Standalone Rebuilder shares these
rules and wiki graph generation; the 70-test Archivist suite still passes.
2026-09-16 Codex — Added portable reviewed-case builder, staged DOHA intake, source-baseline
comparison and publication hashes. Synthetic intake/publish/tamper tests pass;
production corpus unchanged. Legacy regenerator is no longer the canonical route.
2026-09-15 Claude — Corrected mislabelled DD 254 record through the lifecycle process:
chose a `historical` metadata decision (effective 1999-12) over a rename, retirement or
deletion as the least destructive option the contract permits. Evidence: PDF byte-identical
(sha256 264e2155…) to the historical DEC 1999 expired copy; embedded title says December
1999; the recorded official current edition is APR 2018. Added three golden-query cases,
which fail against the prior release and pass against the new one. Published
`dd254-dec1999-lifecycle-fix-20260915`. The first build hung in fastembed workers
(WinError 6 when run under the Git Bash background shell), so I killed it, removed the
partial candidate and rebuilt under PowerShell. The release included the unpublished
2026-09-13 FOCI manifest edits. No source files were changed or deleted. Not committed.
2026-09-15 Codex — Integrated shared source inbox and reviewed-period watch
confirmation into the conductor. Missing evidence now has durable owner routing;
DOHA reconstruction and final role audit remain open.
