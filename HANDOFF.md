# HANDOFF — dcsa-archivist

Last updated: 2026-09-29 by Claude

## Current State
2026-09-29: DOHA LINE ENDINGS. The 20,862 texts published in doha-bulk-all-20260928 are CRLF
(Poppler's Windows default); the 10,633 held texts are LF. The fix is merged (PR #20,
d6b5dbe): the extractor passes `-eol unix`; the reviewed rows in
decisions/doha_robot_line_endings.jsonl (20,862, written by `doha-line-endings-plan`) make the
build rewrite each text as LF with the three stores that hash it (documents.jsonl robot_sha256,
topic index content_sha256/content_bytes, enriched robot_content_sha256); validation refuses any
DOHA text with CR and any store whose hash or indexed copy does not match the file. No rule reads
any decision differently: all readers use read_text, rules re-run reproduce every published
field, the FTS corpus already holds the LF text, and a fresh `-eol unix` extraction of every
published PDF equals the converted text. Design and evidence: docs/DOHA-LINE-ENDINGS.md. 163
tests pass. PUBLISHED 2026-09-29 13:17 UTC on the owner's go-ahead ("publish"):
doha-robot-lf-20260929 (built from main, --deep; validate 0 errors, evaluate 18/18). 20,881 files
copied (20,862 texts, documents.jsonl, DOCUMENTS_ENRICHED, topic index, change summary,
per-release metadata, 3 directive manifests differing only in generated_utc); rollback
.custodian\rollback\20260929T131721461923Z. doctor healthy; all 31,495 DOHA texts LF and every
store agrees (check_texts on the live library: no errors). Handoff event actionable.

Library: 31,495 DOHA decisions since doha-bulk-all-20260928 (2026-09-28 20:24 UTC). The
superseded batch 1 and v1 pilot candidates were recycled at the owner's request; the four
.custodian\doha-pilot-20260927* plan folders remain. Builds re-derive held eras and dates, not
held outcomes, topics or appeal fields (Next 0c). The manual `approve` command now records the
same scope as autonomous publish (release.approval_scope, PR #21).

Owner rules: no DOHA publish without the owner's explicit go-ahead; a DOHA bulk batch needs an
owner spot-check of its plan first. Tests in a worktree need PYTHONPATH=<worktree>\src (the
installed package points at the main checkout); test_source_requests and test_workspace_pipeline
import sibling repos and load only from the main checkout.

## Next
0. DOHA, in order (docs/DOHA-INTAKE.md, docs/DOHA-LINE-ENDINGS.md):
   a. Line endings: DONE (doha-robot-lf-20260929). Its review for Guidance Watch/comparison is
      "line endings only; the text every reader gets is unchanged". Atlas may drop its CRLF shim.
   b. Exceptions (1,079 in plan full-20260928-v8): no case number, undated, no Board order,
      identity mismatches, no outcome, findings conflicts, suffixed keys, scans (OCR). Refetch
      10-03426.h1 via Librarian doha-acquire resume.
   c. Held library: re-run doha-recheck with v8 rules; owner reviews disagreements; build the
      reviewed change (ruling backfills, accepted outcome/topic corrections that rename file and
      ID, a reviewed index migration so appeal fields are searchable). Add the three new appeals
      whose ruling followed DOHA's digest over the Board's Order (Atlas finding): 06-15770.a1 and
      12-01038.a1 were remanded, 14-04825.a1 reversed.
   d. Coverage: Librarian doha-provenance reverse check; only 06-25928.h1 should remain.
   e. Owner to decide: the appeal-link fallback that ignores dates; the SOC source that reads any
      letter in the first 8000 chars; whether CAC decisions stay in DOHA_DECISIONS.
   f. 16 UNDETERMINED decisions (excluded from default retrieval) need review or better text.
1. Source documents.jsonl still says DTM 24-004 and the 2018 handbook "active"; decisions reach
   only DOCUMENTS_ENRICHED and the indexes, and doctor counts unresolved_currency 3 from the
   source. Decide whether publication syncs decided lifecycle; re-check WHS for DTM 24-004.
2. DOHA era changes raise no per-document comparison events; decide whether Question Bot should
   revalidate answers citing a precedent that moved era.
3. Guidance Watch and comparison owe reviews of nist-172-r3-intake-20260911,
   dd254-dec1999-lifecycle-fix-20260915, dd254-canonical-title-20260918, fcl-intake-20260924b,
   doha-bulk-all-20260928 and doha-robot-lf-20260929; acknowledge only with hashed receipts.
4. When the Librarian's ledger has verified provenance rows: import-provenance, then
   build/validate/evaluate/publish (the Rebuilder's 749 retained-bytes-only records).

## Open Questions
None open.

## Log
Older entries, and this file as it stood before the 2026-09-29 trim: HANDOFF-archive.md.
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
2026-09-28 Claude (local) — CRLF in the new DOHA texts, flagged by the Atlas rebuild. Survey of
all 31,495: new pure CRLF, held pure LF. The pipeline was never affected (read_text); rules re-run
on all 20,862 match the published metadata; read raw, 2 decisions' topics would differ, which is
what a byte-level consumer hit. The hash lives in three live stores; no sibling repo holds it.
Chose byte conversion over re-extraction (same bytes, no Poppler at build).
2026-09-28 Claude (Atlas rebuild) — Findings from rebuilding the Adjudication Atlas on this
release (Atlas REPORT.md v1.9): the CRLF texts above; and in 3 of 4,311 new appeals the intake's
ruling follows DOHA's digest where it contradicts the Board's Order (Next 0c).
2026-09-28 Claude (local) — Owner said "Go ahead": dry run first (41,750 changed files; no
existing decision overwritten), then published doha-bulk-all-20260928 (8 min). doctor healthy.
DOHA intake of the 20,862 acquired decisions is complete; exceptions and held-library
corrections remain. Provenance rows committed (PR #19).
2026-09-28 Claude (local) — Review v8 merged (PR #18): a guideline the decision says was not
alleged is no topic (30 decisions lose a letter, none gain). Combined candidate built from the v8
plan in 42 min (batch 1 alone took 89 on the old code), validate clean, evaluate 18/18. Owner
chose one publish for the whole corpus instead of four batches.
