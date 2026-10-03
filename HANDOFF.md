# HANDOFF — dcsa-archivist

Last updated: 2026-09-29 by Claude

## Current State
2026-10-03: DOHA REVIEW v9, IN PROGRESS (branch claude/doha-review-v9, rebased on main; nothing
built or published). v9 reads the caption/header variants, 1996-97 opening date lines, Board order
and hearing conclusion wordings found among v8's exceptions, and holds back SORs in the pre-1996
criteria lettering (docs/DOHA-INTAKE.md "Review v9"). Against v8 on every text: held decisions
only gain readings; four published ones read differently (on the 0c sheet). Re-plan
doha-plans\full-20260929-v9b: 585 planned, 494 exceptions (of 1,079). Spot-check 1 (seed 20261003)
found a v9 bug (97-00752.a1, a reversed finding read as a reversed decision; fixed). Spot-check 2
(seed 20261004, full-20260929-v9b\spotcheck-v9.csv): Claude's pre-marks 19/20; the N, 95-00863.h1
(pre-1996 lettering), is now held back. Final plan doha-plans\full-20261003-v9c: 584 planned, 495
exceptions (= v9b less 95-00863.h1). Sheets there: spotcheck-v9c-premarked.csv (40), -verify.csv
(7). OWNER VERIFIED all 7 rows (2026-10-03). Next: v9 on main (PR #24); then provenance append,
build-candidate --intake-plan, validate, evaluate, owner go-ahead, publish.

Line endings done (doha-robot-lf-20260929; docs/DOHA-LINE-ENDINGS.md). Since then Codex published
voi-20260930-v3 (2026-10-01; 32,498 documents), which touched no DOHA store.

Library: 31,495 DOHA decisions since doha-bulk-all-20260928 (2026-09-28 20:24 UTC). The
superseded batch 1 and v1 pilot candidates were recycled at the owner's request; the four
.custodian\doha-pilot-20260927* plan folders remain. Builds re-derive held eras and dates, not
held outcomes, topics or appeal fields (Next 0c). The manual `approve` command now records the
same scope as autonomous publish (release.approval_scope, PR #21).

Owner rules: no DOHA publish without the owner's explicit go-ahead; a DOHA bulk batch needs an
owner spot-check of its plan first. Tests in a worktree need PYTHONPATH=<worktree>\src (the
installed package points at the main checkout); the cross-repo tests find the workspace by walking
up (tests/_workspace.py), so they run from worktrees too.

## Next
0. DOHA, in order (docs/DOHA-INTAKE.md, docs/DOHA-LINE-ENDINGS.md):
   a. Line endings: DONE (doha-robot-lf-20260929). Its review for Guidance Watch/comparison is
      "line endings only; the text every reader gets is unchanged". Atlas may drop its CRLF shim.
   b. Exceptions (the v9 session's): v9 settles 585 of v8's 1,079. Of the rest: 7 WordPerfect
      files DOHA serves as .pdf (need a converter), ~100 that state no date anywhere (owner: plan
      with a listing-bounded era and no date?), identity conflicts for a person (listing-label
      typos, redacted captions), ~160 unsettled topics (not yet diagnosed), 22 suffixed keys,
      5 scans. Refetch 10-03426.h1 via Librarian doha-acquire resume.
   c. Held library (Claude takes it once review v9 is on main; 0b is the v9 session's): re-run
      doha-recheck with v9 rules; owner reviews disagreements; build the reviewed change (ruling
      backfills, accepted outcome/topic corrections that rename file and ID, a reviewed index
      migration so appeal fields are searchable). Put on the sheet the Atlas's three (06-15770.a1
      and 12-01038.a1 remanded, 14-04825.a1 reversed; ruling followed the digest over the Order)
      and v9's four: 04-11414.a1 (same pattern), 08-07803.h1 and 10-03757.h1 (outcome conflicts),
      06-20964.a1 (appealed_by probably Department Counsel). Also the published ones v9 holds back
      for the pre-1996 lettering (topic I there is poor judgment): 95-00566.h1, 95-00622.a1,
      95-00817.a1, 95-00818.a1, 95-00904.a1, 95-00918.a1, and 96-00460.h1 (check).
   d. Coverage: Librarian doha-provenance reverse check; only 06-25928.h1 should remain.
   e. Owner to decide: the appeal-link fallback that ignores dates; the SOC source that reads any
      letter in the first 8000 chars; whether CAC decisions stay in DOHA_DECISIONS.
   f. 16 UNDETERMINED decisions (excluded from default retrieval) need review or better text.
1. Source documents.jsonl still says DTM 24-004 and the 2018 handbook "active"; decisions reach
   only DOCUMENTS_ENRICHED and the indexes, and doctor counts unresolved_currency 3 from the
   source. Decide whether publication syncs decided lifecycle; re-check WHS for DTM 24-004.
2. DOHA era changes raise no per-document comparison events; decide whether Question Bot should
   revalidate answers citing a precedent that moved era.
3. Guidance Watch and comparison owe reviews of older release events (Oct 2 Supervisor: five
   comparison, six Guidance Watch); comparison acknowledged doha-robot-lf-20260929 as no relevant
   change. Acknowledge only with hashed receipts.
4. When the Librarian's ledger has verified provenance rows: import-provenance, then
   build/validate/evaluate/publish (the Rebuilder's 749 retained-bytes-only records).

## Open Questions
None open.

## Log
Older entries, and this file as it stood before the 2026-09-29 trim: HANDOFF-archive.md.
2026-10-03 Claude — 0b by review v9: rules from samples of each v8 exception reason, measured
against v8 on every text before any re-plan; spot-checks stratified by v8 reason (first found a
v9 bug, second the pre-1996 lettering). 0c: the session that took it has ended; see Next 0c.
2026-09-29 Claude — test_source_requests and test_workspace_pipeline counted parent folders to
find the workspace, which fails in a worktree; tests/_workspace.py walks up instead. 165 pass.
2026-09-29 Claude — Owner merged PR #20. Candidate diffed against the live library: only the
planned fields change (robot_sha256; index content_sha256/content_bytes; corpus text and topics
identical; change packet = the 20,862 planned, robot_content_sha256 only). Enriched records of the
new decisions also gain current_group/doha_group/retrieval_priority, absent since the intake build
(values agree with the era manifest). Merging is the owner's step (auto mode refuses self-merge).
Owner said "publish": published doha-robot-lf-20260929; doctor healthy; library all LF.
2026-09-29 Claude — Manual `approve` hardcoded scope derived_artifacts_only; it and autonomous
publish now share release.approval_scope (LIBRARY_STATE source_intake_files decides).
tests/test_approval_scope.py covers both kinds (fails on the old code); 165 tests pass. PR #21.
2026-09-29 Claude — Owner said "go do the things". Implemented the LF rewrite as a reviewed input
(like retirements: rows stay after publication and then count as already applied; the build
fails closed if a text no longer matches its row) rather than a one-off script, so the change is
built, validated and published like any other. Code only in doha_release/release/cli, not in the
modules the Rebuilder vendors. The patches share one staged copy of documents.jsonl and the topic
index with the era patch, and the index's full text is not touched (already LF). Test fixtures
that wrote DOHA text with platform line endings now write LF; the new check caught one. Rows
generated from the live library match last night's survey hash for hash (20,862/20,862).
Trimmed this file to the 100-line cap (it was ~495 lines).
2026-09-28 Claude (Atlas rebuild) — Findings from rebuilding the Adjudication Atlas on this
release (Atlas REPORT.md v1.9): the CRLF texts (since fixed); and in 3 of 4,311 new appeals the
intake's ruling follows DOHA's digest where it contradicts the Board's Order (Next 0c).
2026-09-28 Claude (local) — Owner said "Go ahead": dry run first (41,750 changed files; no
existing decision overwritten), then published doha-bulk-all-20260928 (8 min). doctor healthy.
DOHA intake of the 20,862 acquired decisions is complete; exceptions and held-library
corrections remain. Provenance rows committed (PR #19).
