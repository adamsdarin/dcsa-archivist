# HANDOFF — dcsa-archivist

Last updated: 2026-10-03 by Claude (merged with Codex's uncommitted 2026-10-02 handoff)

## Current State
Archivist validates source identity, parity, taxonomy, lifecycle, retrieval quality and release
readiness; it is the only system that publishes approved-library releases, after all gates pass.

Current release voi-20260930-v3 (Codex, 2026-10-01): the September 2026 VOI passed identity,
provenance, byte retention, parity, validation and retrieval evaluation and was published
autonomously; 32,498 documents, 16,112 chunks, doctor healthy, eight verified indexes. The other
monthly-scan packages stay outside it (2026-10-01: 7 exact duplicates, 73 blocked on coverage).
Consumers (Oct 2 Supervisor): dcsa-compare acknowledged the VOI and doha-robot-lf-20260929
(no_relevant_change); Guidance Watch acknowledged the VOI; five comparison and six Guidance Watch
events remain pending.

DOHA REVIEW v9 merged (PR #24, 2026-10-03). It reads the caption/header variants, 1996-97 opening
date lines, Board order and hearing conclusion wordings found among v8's 1,079 exceptions, and
holds back SORs in the pre-1996 criteria lettering (docs/DOHA-INTAKE.md "Review v9"). Plan
doha-plans\full-20261003-v9c: 584 planned, 495 exceptions. Two seeded spot-checks (40 decisions,
sheets in the plan folder) found a v9 bug and the old lettering, both fixed; OWNER VERIFIED all 7
verify rows (2026-10-03). Next: provenance append (dry run clean: 584 rows), build-candidate
--intake-plan, validate, evaluate, publish --dry-run, owner go-ahead, publish.

DOHA library: 31,495 decisions; line endings done (doha-robot-lf-20260929; all LF, validation
refuses CR). Builds re-derive held eras and dates, not held outcomes, topics or appeal fields
(Next 0c). Manual `approve` records the same scope as autonomous publish (PR #21).

Owner rules: no DOHA publish without the owner's explicit go-ahead; a DOHA bulk batch needs an
owner spot-check of its plan first. Tests in a worktree need PYTHONPATH=<worktree>\src (the
installed package points at the main checkout); cross-repo tests find the workspace by walking up.

## Next
0. DOHA, in order (docs/DOHA-INTAKE.md, docs/DOHA-LINE-ENDINGS.md):
   a. Line endings: DONE (doha-robot-lf-20260929); comparison acknowledged it. Atlas may drop its
      CRLF shim.
   b. Exceptions: v9 published 584 (Current State). Of the 495 left: 7 WordPerfect files
      DOHA serves as .pdf (owner: convert with LibreOffice?), ~100 that state no date anywhere
      (owner: plan with a listing-bounded era and no date?), identity conflicts for a person
      (listing-label typos, redacted captions), ~160 unsettled topics (not yet diagnosed), the
      pre-1996 lettering (owner: reviewed mapping or exceptions?), 22 suffixed keys, 5 scans.
      Refetch 10-03426.h1 via Librarian doha-acquire resume.
   c. Held library (the "Fix approve command" Claude session has it; recheck with v9 rules from
      main 24d6f98 running 2026-10-03, output under doha-plans): owner reviews disagreements; build the reviewed change (ruling backfills, accepted
      outcome/topic corrections that rename file and ID, a reviewed index migration so appeal
      fields are searchable). On the sheet: the Atlas's three (06-15770.a1 and 12-01038.a1
      remanded, 14-04825.a1 reversed; ruling followed the digest over the Order); v9's four:
      04-11414.a1 (same pattern), 08-07803.h1 and 10-03757.h1 (outcome conflicts), 06-20964.a1
      (appealed_by probably Department Counsel); and the published ones v9 holds back for the
      pre-1996 lettering (topic I there is poor judgment): 95-00566.h1, 95-00622.a1, 95-00817.a1,
      95-00818.a1, 95-00904.a1, 95-00918.a1, and 96-00460.h1 (check).
   d. Coverage: Librarian doha-provenance reverse check; only 06-25928.h1 should remain.
   e. Owner to decide: the appeal-link fallback that ignores dates; the SOC source that reads any
      letter in the first 8000 chars; whether CAC decisions stay in DOHA_DECISIONS.
   f. 16 UNDETERMINED decisions (excluded from default retrieval) need review or better text.
1. Source documents.jsonl still says DTM 24-004 and the 2018 handbook "active"; decisions reach
   only DOCUMENTS_ENRICHED and the indexes, and doctor counts unresolved_currency 3 from the
   source. Decide whether publication syncs decided lifecycle; re-check WHS for DTM 24-004.
2. DOHA era changes raise no per-document comparison events; decide whether Question Bot should
   revalidate answers citing a precedent that moved era.
3. Preserve voi-20260930-v3's rollback and event evidence. Guidance Watch's six and comparison's
   five older events stay pending until their own full-source, citation and coverage gates pass;
   acknowledge only with separate hashed receipts.
4. Monthly-scan packages: 73 blocked on incomplete coverage (Codex, 2026-10-01); no build.
5. When the Librarian's ledger has verified provenance rows: import-provenance, then
   build/validate/evaluate/publish (the Rebuilder's 749 retained-bytes-only records).

## Open Questions
The DOHA policy questions in Next 0b and 0e wait on the owner.

## Log
Older entries, and this file as it stood before the 2026-09-29 trim: HANDOFF-archive.md.
2026-10-03 Claude — Owner said "publish": published doha-v9-exceptions-20261003 (584 decisions)
after validate, evaluate 18/18, a store-by-store diff and a dry run; doctor healthy.
2026-10-03 Claude — Merged Codex's uncommitted 2026-10-02 rewrite of this file (VOI release and
consumer state) with the DOHA state from PR #24; Codex's archive additions kept. Three older
Claude entries moved to the archive.
2026-10-03 Claude — 0b by review v9: rules from samples of each v8 exception reason, measured
against v8 on every text before any re-plan; spot-checks stratified by v8 reason (first found a
v9 bug, second the pre-1996 lettering). Owner verified the spot-check and merged PR #24.
2026-10-02 Codex — Verified the hash-bound dcsa-compare receipt for doha-robot-lf-20260929; the
Supervisor reports five comparison and six Guidance Watch events pending. Guidance Watch's
separate September VOI receipt is complete; no older blocked event was acknowledged.
2026-10-01 Codex — Published scoped release voi-20260930-v3 after validation and 18/18 retrieval
evaluation passed. Post-publication doctor healthy (32,498 documents; 16,112 chunks; eight
verified indexes). Comparison acknowledged; Guidance Watch pending on its own coverage gate.
2026-10-01 Codex — Recorded 81-package review dispositions and an incomplete-coverage blocker:
seven exact duplicates, one verified September VOI pending full coverage, 73 packages still
blocked; no build or publication. Integrity audit passed (32,497, no findings).
2026-09-29 Claude — test_source_requests and test_workspace_pipeline counted parent folders to
find the workspace, which fails in a worktree; tests/_workspace.py walks up instead. 165 pass.
2026-09-29 Claude — Owner merged PR #20; candidate diffed against the live library (only the
planned fields change). Owner said "publish": published doha-robot-lf-20260929; doctor healthy.
2026-09-29 Claude — Manual `approve` hardcoded scope derived_artifacts_only; it and autonomous
publish now share release.approval_scope (LIBRARY_STATE source_intake_files decides). PR #21.
