# HANDOFF — dcsa-archivist

Last updated: 2026-09-27 by Claude

## Current State
2026-09-27: DOHA bulk intake is NOT complete. Library holds 10,633 DOHA decisions;
~21,890 more are downloaded (Librarian run quarantine/doha-acquire/20260925T151200Z)
and not yet planned. Pilot `doha-pilot-20260927` (48 decisions): build valid and
publishable, validate 0 errors/0 blockers, evaluate 18/18; NOT published. Claude
recommended not publishing it separately (its decisions ride in batch 1); owner to decide.
evaluate asks no DOHA questions, so it proves only that regulation search is intact.
Accuracy is unmeasured: owner spot-checked 5 pilot decisions (all correct after the
affirmed/denied fix). Added doha_quality.py: doha-plan-batches, doha-accuracy-sample,
doha-accuracy-score (one-sided 95% Clopper-Pearson bound vs an agreed target),
doha-recheck (rules over held decisions: disagreements, unsettled, appeal/remand
backfill proposals, two review sheets), doha-append-provenance. Workflow in
docs/DOHA-INTAKE.md. **Owner rule: no DOHA bulk batch is published before the owner
spot-checks a sample; do not approve/publish without explicit go-ahead.**
Remaining known gaps: 10-03426.h1 needs refetch (empty package); 06-25928.h1 exists
only as a DOHA digest; 2 pilot exceptions (30-01130.a1 docket typo, 97-00053.h1
underscore date). 8 test errors in this cloud environment predate this work
(fastembed and sibling repos absent); 132 pass.

2026-09-24: Published `fcl-intake-20260924b` (autonomous after gates: validate valid/publishable, 0 errors,
0 blockers; evaluate 18/18; doctor integrity_healthy, production_response_ready, 8 verified indexes).
Change set is exactly 16 records: 13 added (12 DCSA FCL documents from Librarian quarantine
20260924T122142Z into INDUSTRIAL_SECURITY/TOOLS/DCSA_ISSUED_JOB_AIDS, plus the reviewed 2005 Adjudicative
Guidelines, superseded/historical) and 3 lifecycle changes. The March 2021 and October 2018 FCL Orientation
Handbooks are `superseded` (historical_only), superseded_by dcsa-job_aids-fcl-orientation-handbook-2026-07,
labelled inferred_pending_review because DCSA states no supersession. DTM 24-004 is `currency_unresolved`
(current_or_verify, unresolved-research index only): past its own 2026-07-31 expiration, still listed by WHS,
no cancellation recorded. Byte-verified official URLs now on SF 328, DoDM 5220.32 V1/V2 and DTM 24-004.
Seven pages carry only image content (diagrams, sample org charts, annotated DD 441/SF 328); their robot text
appends a marked "[Archivist transcription ...]" block and text_quality says so. Code: `currency_unresolved`
disposition, provenance riding on lifecycle decisions, in-process fastembed on Windows. 100 tests pass.
Was left uncommitted; committed 2026-09-27 from the owner's working tree (branch
wip/archivist-local-2026-09-27) and merged with doha-intake-plan.

2026-09-23: Published `doha-retire-phantom-rows-20260923` (autonomous after gates:
validate valid/publishable, evaluate 16/16, doctor healthy, doha_era_inconsistencies 0).
Retired the 25 DOHA rows that named a robot text file and a source PDF the library
does not hold. None was ever in documents.jsonl, and each duplicated a case the
library does hold under another row with byte-identical indexed text, so nothing was
lost: all 25 survivors are still there with both artifacts. One of the 25 was
answer-eligible and inside the Question Bot's default precedent filter, so a real
answer could have cited a path that does not exist. The DOHA stores now hold 10,633
decisions, every one with its text, its PDF and a source URL.

A reviewed retirement (decisions/doha_retired_rows.json) drops a row from both DOHA
manifests and deletes it from both DOHA indexes, including decision_topics and the
FTS corpus. The build re-checks every condition and refuses a retirement whose files
exist, whose document the source manifest carries, or whose indexed text differs from
the row said to supersede it. Validation now fails any candidate that still promises
robot text the library does not hold, so the next phantom row blocks a release rather
than reaching consumers. 95 tests pass.

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
0. DOHA completion, in order (docs/DOHA-INTAKE.md): full doha-intake-plan; owner checks
   doha-accuracy-sample sheet, doha-accuracy-score must pass the agreed target; doha-recheck
   over held decisions and owner review of its sheets; batches of ~5,500 with per-batch
   provenance append, build, validate, evaluate, owner sign-off, publish; Librarian
   reverse check at the end. Still to build after the recheck is reviewed: applying
   ruling_backfill.jsonl and accepted corrections to held records (a reviewed decisions
   file applied at build, like doha_era_reviews.json) and a reviewed DOHA index
   migration so appeal fields are searchable.
0. Decisions reach DOCUMENTS_ENRICHED.jsonl and the indexes, not the source documents.jsonl, which still
   says DTM 24-004 "active" (and the 2018 handbook "active"); `doctor` counts unresolved_currency from the
   source manifest, so it still reports 3. Decide whether publication should sync decided lifecycle into
   documents.jsonl. Re-check WHS for a DTM 24-004 extension, cancellation or incorporation.
   Guidance Watch and comparison owe review of event fcl-intake-20260924b.
1. 16 DOHA decisions are UNDETERMINED (release report, doha-retire-phantom-rows-20260923).
   Each needs a reviewed decision or a better extraction; they are excluded from
   default retrieval until then. Their texts state no usable date, or state one
   their own record contradicts, and all sit within weeks of 2017-06-08.
2. DOHA era changes deliberately raise no per-document comparison events (the
   change packet tracks source and lifecycle fields, not era). Consumers read
   DOHA_SEAD4_RETRIEVAL_RULES.json and the release report instead. If Question Bot
   should revalidate wiki answers citing a precedent that moved era, that has to be
   decided and built.
3. Guidance Watch and comparison still owe reviews for four release events
   (nist-172-r3-intake-20260911, dd254-dec1999-lifecycle-fix-20260915,
   dd254-canonical-title-20260918, fcl-intake-20260924b); acknowledge only with
   their separate hashed receipts.
4. When the Librarian's ledger has verified provenance rows, run import-provenance,
   then build/validate/evaluate/publish. That is how the Rebuilder's 749
   retained-bytes-only records gain official URLs.
5. Continue the shared audit; DOHA implementation is in docs/DOHA-INTAKE.md.

## Open Questions
None open. The DD 254 relabel question (options a/b/c) was resolved on 2026-09-18
with option (c) plus a reviewed canonical choice, at the owner's direction.

## Log
2026-09-27 Claude — v3's cross-check doubled exceptions (1,110 to 2,148): 969 "denied but
findings all for". Samples from the owner's machine showed three reader gaps in older
(2000-2002) layouts, not contradictions: findings written "AGAINST THE APPLICANT";
the order under a bare "DECISION" heading, so the findings section ran into footnotes
("the case against Applicant"); and synopses like "precludes a finding that it is
clearly consistent ... to grant" read as a grant. Fixed all three (the negation check
applies to the grant phrase only, so "has not mitigated ... not clearly consistent"
stays a denial). Same "the" gap explained most of the remaining topic mismatches.
Reviewer v4. Owner asked to choose topic meaning (all SOR guidelines vs KEYWORD only).
2026-09-27 Claude — Owner checked 5 outcome conflicts between the held library and the
rule: library wrong on 2 hearings, rule wrong on 1 (19-01803.h1), 2 appeals pending the
owner's detail. The rule's error was a judge's slip ("clearly consistent ... to grant
... is denied") where the grant phrase ("national security of the United States")
was not recognised. Hearing outcomes are now cross-checked against the opening summary
and the formal findings: any contradiction of a clear conclusion is an exception, and a
missing or self-contradicting conclusion is settled only when summary and findings
agree. Stricter, so expect more exceptions and fewer wrong labels. Reviewer v3.
2026-09-27 Claude — First full runs: plan 20,831 planned / 1,110 exceptions of 21,941;
re-check of 10,633 held. The re-check's 3,852 topic "disagreements" were mostly its own
bug (legacy index rows store codes space-separated, "E I J"); fixed. A real topic-rule
gap remained: a KEYWORD line was trusted if any segment matched, so "Financial ;
Personal Conduct" lost F and "Security Violations" (1997 name for K) was dropped. Now
every published guideline name (1997/2006/2017) and unique first words map, and a
segment naming no guideline adds the formal findings instead of dropping a topic.
Reviewer bumped to v2; the full plan must be regenerated. 21 held decisions have no
stored outcome (reported as outcome_missing, not conflicts).
2026-09-27 Claude — Owner asked whether DOHA work is complete and accurate: it is not
(32% of DOHA's rulings held; accuracy never measured). Built measurement rather than
more spot checks: a seeded proportional-stratified sample scored by a one-sided 95%
upper bound, because "5 of 5 correct" bounds nothing (95% bound 45%). Rare rulings get
unscored edge draws so the estimate stays unbiased. Held decisions are re-checked by the
same rules and every disagreement is listed for review, not auto-corrected: either side
may be wrong. Batches keep a case together so appeal links resolve within one release.
2026-09-27 Claude — Added an embedding cache (.custodian/embedding_cache.sqlite). Every build
re-embedded all ~16,100 chunks although only new or edited documents change them; vectors
are now keyed by model name and the SHA-256 of the exact chunk text, so a changed chunk or
model misses and is re-embedded. Only the real model's vectors are cached: a substituted
embedder (the tests' zero-vector fakes) bypasses it, so a fake can never be served to a
real build. DCSA_EMBED_CACHE=0 disables it; each build reports hits in EMBEDDING_CACHE.json.
The first DOHA pilot build (48 decisions) was valid and publishable; not published.
2026-09-27 Claude — Appeals now record what the Board did (affirmed/reversed/remanded) and
which hearing decision it reviewed, per the owner. Kept `outcome` as where the clearance
ends up rather than replacing it: "affirmed" alone does not say whether a clearance was
granted, and the outcome is embedded in 10,633 existing IDs and paths and in both
consumers' filters. The reviewed decision is the latest hearing decision dated before
the appeal, else the case's only one, else the same-numbered one, each with its basis.
2026-09-27 Claude — Committed and merged the 2026-09-24 session's uncommitted work (it
built and published fcl-intake-20260924b from an uncommitted tree). Needed before any
further build: the already-retired DOHA rows fix (main would refuse every build, the
25 retirements being live) and in-process fastembed on Windows (builds hung).
2026-09-27 Claude — Added doha-intake-plan. Rules over an LLM pass: DOHA decisions are
regular enough that identity, date, era, outcome and topics can be read by rule with
the quoted evidence kept, so every run is repeatable; judgement is reserved for the
exceptions list. Topics match only within the KEYWORD line, because aliases like
"debt" or "arrest" would mis-tag anywhere in a decision. Per-batch owner sign-off is
stricter than the autonomous-publish default, at the owner's choice.
2026-09-25 Codex — Supervisor and consumer packet refresh show four pending events. Comparison verified only that the two historical DD 254 robot texts are identical; broader lifecycle/citation review is incomplete. Guidance Watch also reports full-source and product-disposition gaps. No consumer receipts or acknowledgements were created.
2026-09-24 Claude — Published fcl-intake-20260924b. Chose to include the already-reviewed 2005 Adjudicative
Guidelines item rather than strip its pending decision, because that decision fails every build without it
and the 2026-09-23 owner-authorized review was complete. Chose `superseded` with label inferred_pending_review
for the old handbooks (owner asked; same publisher, same title, newer edition; no explicit DCSA statement).
Added `currency_unresolved` rather than inventing a DTM cancellation or leaving "active". Transcribed
image-only pages with explicit markers instead of leaving diagrams and form annotations unretrievable.
Librarian doctor's doha_topic_* keys were a stale check (entry lacks them in every rollback since 09-09;
Archivist doctor is the governing contract); fixed in dcsa-librarian with tests.
2026-09-24 Claude — CHECKPOINT (in progress): FCL intake from Librarian quarantine 20260924T122142Z.
Reviewed plan at .custodian/incoming/fcl-20260924/INTAKE-PLAN.json (12 FCL items + the 2026-09-23
Adjudicative Guidelines 2005 item, whose uncommitted decision blocks any build without it). Decisions:
2018/2021 handbooks superseded, DTM 24-004 currency_unresolved (new disposition), provenance attached.
Uncommitted drift found at start (not in log): the DOHA already-retired fix in doha_release.py + test and
the AG-2005 superseded decision, from an unfinished 2026-09-23 session whose build crashed in fastembed.
2026-09-24 Claude — fastembed hang: build fcl-intake-20260924 (PowerShell, background) died in fastembed's
multiprocessing pool (parallel=20 for >=200 texts): three worker "OSError: [WinError 6] The handle is invalid"
in parallel_processor/multiprocessing queues, then the parent sat idle (0 CPU, log still 23 min). Same failure as
2026-09-23, so it is not a Git-Bash-only issue as the 2026-09-15 note assumed. Stopped only that PID. Fix:
semantic.embedding_workers() — Windows defaults to in-process (parallel=None); DCSA_EMBED_PARALLEL overrides
(0/1 in-process, N>1 workers). Same model, batch size and normalization, so vectors are unchanged; only the
execution mode differs. Test added; 100 tests pass. Rebuilt as fcl-intake-20260924b.
2026-09-23 Claude — Retired 25 phantom DOHA rows rather than restoring text for them.
Restoring was not an option worth taking: the source PDF is missing too, so a restored
file would be a robot artifact with no source, and the same text is already served by a
row that has both. Retirement is gated on four conditions checked at build time, because
the difference between a phantom row and a real document whose file went missing is
exactly the difference between cleanup and data loss.
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
