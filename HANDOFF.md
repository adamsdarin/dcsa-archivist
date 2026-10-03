# HANDOFF - dcsa-archivist

Last updated: 2026-10-03 by Claude

## Current State
Archivist validates source identity, parity, taxonomy, lifecycle, retrieval quality and release readiness; it is the only system that publishes approved-library releases after all gates pass without blockers.

The September 2026 VOI passed identity, provenance, original-byte retention, text parity, validation and retrieval evaluation. Candidate `voi-20260930-v3` was published autonomously after all Archivist release gates passed. The library now contains 32,498 documents and 16,112 chunks; post-publication doctor reports a healthy, production-ready release with eight verified indexes. The other monthly-scan packages remain outside this scoped VOI release.

The `dcsa-compare` consumer completed the September VOI event and acknowledged the DOHA line-ending-only event `doha-robot-lf-20260929` as `no_relevant_change` with a hash-bound receipt on Oct 2. Five older comparison events remain pending. Guidance Watch completed the September VOI product review and acknowledged it with a separate receipt; six older Guidance Watch events remain pending. The Oct 2 Supervisor confirms the current release `voi-20260930-v3` and these separate consumer counts.

DOHA: 31,495 decisions held since doha-bulk-all-20260928; every text LF since doha-robot-lf-20260929
(rollback .custodian\rollback\20260929T131721461923Z; validation refuses CR in DOHA text,
docs/DOHA-LINE-ENDINGS.md). Review v9 is in progress in another Claude session (worktree
optimistic-williamson-4bb90e, unpushed branch claude/doha-review-v9, last commit 2026-09-29): per its
notes it settles 585 of v8's 1,079 exceptions, and tests, a v9c re-plan and an owner spot-check come
before its PR. Builds re-derive held eras and dates, not held outcomes, topics or appeal fields
(Next 0c). The four .custodian\doha-pilot-20260927* plan folders remain.

Owner rules: no DOHA publish without the owner's explicit go-ahead; a DOHA bulk batch needs an
owner spot-check of its plan first. Tests in a worktree need PYTHONPATH=<worktree>\src (the
installed package points at the main checkout); the cross-repo tests find the workspace by walking
up (tests/_workspace.py), so they run from worktrees too.

## Next
0. DOHA, in order (docs/DOHA-INTAKE.md, docs/DOHA-LINE-ENDINGS.md):
   a. Line endings: DONE (doha-robot-lf-20260929); comparison acknowledged it on Oct 2. Atlas may
      drop its CRLF shim.
   b. Exceptions (1,079 in plan full-20260928-v8; the v9 session owns this): no case number,
      undated, no Board order, identity mismatches, no outcome, findings conflicts, suffixed keys,
      scans (OCR). Refetch 10-03426.h1 via Librarian doha-acquire resume.
   c. Held library (Claude takes it once review v9 is on main): re-run doha-recheck with v9 rules;
      owner reviews disagreements; build the reviewed change (ruling backfills, accepted
      outcome/topic corrections that rename file and ID, a reviewed index migration so appeal
      fields are searchable). Put on the sheet the Atlas's three (06-15770.a1 and 12-01038.a1
      remanded, 14-04825.a1 reversed; ruling followed the digest over the Order) and v9's four:
      04-11414.a1 (same pattern), 08-07803.h1 and 10-03757.h1 (outcome conflicts), 06-20964.a1
      (appealed_by probably Department Counsel).
   d. Coverage: Librarian doha-provenance reverse check; only 06-25928.h1 should remain.
   e. Owner to decide: the appeal-link fallback that ignores dates; the SOC source that reads any
      letter in the first 8000 chars; whether CAC decisions stay in DOHA_DECISIONS.
   f. 16 UNDETERMINED decisions (excluded from default retrieval) need review or better text.
1. Preserve `voi-20260930-v3` as the current approved release and its rollback/event evidence.
2. Preserve the completed Guidance Watch receipt for `voi-20260930-v3`; keep its six older events pending until their full-source, citation and coverage gates pass.
3. Resolve the five older pending comparison events separately; the DOHA line-ending-only event is complete.
4. Source documents.jsonl still says DTM 24-004 and the 2018 handbook "active"; decisions reach
   only DOCUMENTS_ENRICHED and the indexes, and doctor counts unresolved_currency 3 from the
   source. Decide whether publication syncs decided lifecycle; re-check WHS for DTM 24-004.
5. DOHA era changes raise no per-document comparison events; decide whether Question Bot should
   revalidate answers citing a precedent that moved era.
6. When the Librarian's ledger has verified provenance rows: import-provenance, then
   build/validate/evaluate/publish (the Rebuilder's 749 retained-bytes-only records).

## Open Questions
Owner decisions are listed in Next 0e, 4 and 5.

## Log
Newest first. Older entries, and this file as it stood before each trim: HANDOFF-archive.md.
2026-10-03 Claude - Merged Codex's uncommitted 2026-10-02 refresh (VOI release, consumer receipts;
prior text archived) with main's DOHA state, owner rules and Next list, which it had archived; it
was written before PR #23. Codex's entries below are reordered newest first, text unchanged.
2026-10-02 Codex - Verified the hash-bound `dcsa-compare` receipt for `doha-robot-lf-20260929`; the Supervisor now reports five comparison and six Guidance Watch events pending. Guidance Watch's separate September VOI receipt is complete; no older blocked event was acknowledged.
2026-10-01 Codex - Published scoped release `voi-20260930-v3` after validation and 18/18 retrieval evaluation passed. Post-publication doctor is healthy (32,498 documents; 16,112 chunks; eight verified indexes). Comparison review acknowledged; Guidance Watch remains pending on its own coverage gate.
2026-10-01 Codex - Recorded 81-package review dispositions and incomplete coverage blocker. Seven exact duplicates, one verified September VOI pending full coverage, 73 packages still blocked; no build or publication. Integrity audit passed (32,497, no findings).
2026-09-29 Claude - test_source_requests and test_workspace_pipeline counted parent folders to
find the workspace, which fails in a worktree; tests/_workspace.py walks up instead. 165 pass.
2026-09-29 Claude - Owner merged PR #20. Candidate diffed against the live library: only the
planned fields change (robot_sha256; index content_sha256/content_bytes; corpus text and topics
identical). Merging is the owner's step (auto mode refuses self-merge). Owner said "publish":
published doha-robot-lf-20260929; doctor healthy; library all LF.
2026-09-29 Claude - Manual `approve` hardcoded scope derived_artifacts_only; it and autonomous
publish now share release.approval_scope (LIBRARY_STATE source_intake_files decides). PR #21.
2026-09-29 Claude - Implemented the DOHA LF rewrite as a reviewed input (like retirements), so it
is built, validated and published like any other change; code only in doha_release/release/cli.
2026-09-28 Claude (local) - CRLF in the new DOHA texts, flagged by the Atlas rebuild; the pipeline
was never affected (read_text). Chose byte conversion over re-extraction.
2026-09-28 Claude (Atlas rebuild) - In 3 of 4,311 new appeals the intake's ruling follows DOHA's
digest where it contradicts the Board's Order (Next 0c).
2026-09-28 Claude (local) - Published doha-bulk-all-20260928 on the owner's go-ahead; DOHA intake
of the 20,862 acquired decisions is complete; exceptions and held-library corrections remain.
