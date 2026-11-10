# HANDOFF — dcsa-archivist

Last updated: 2026-11-03 by Claude

## Current State

Current approved release is `doha-new-20261103`, published 2026-11-03 on the owner's go-ahead (33,202 documents, doctor healthy). It adds 119 DOHA decisions and brings the October 2026 VOI, which was in the live manifest outside any release, under a governed release. Its comparison and Guidance Watch event is pending. 11 decisions are held out pending reviewed values proposed to the owner. The paragraph below is the older state of the v9 release.

Current approved release `doha-v9-exceptions-20261003` adds 584 tier-5 DOHA adjudicative-precedent records only; all are marked not independently binding and exact-case-only, and no existing record changed. The new release event remains pending for both consumers because full-source/citation/product-coverage review and receipts are incomplete. The interrupted Librarian retry left 109 quarantined packages from four sources for identity, parity, and lifecycle review; do not build a candidate until those gates and monthly-source coverage are complete.

Line endings done (doha-robot-lf-20260929; docs/DOHA-LINE-ENDINGS.md). Since then Codex published
voi-20260930-v3 (2026-10-01; 32,498 documents), which touched no DOHA store.

Library: 31,495 DOHA decisions since doha-bulk-all-20260928 (2026-09-28 20:24 UTC). The
superseded batch 1 and v1 pilot candidates were recycled at the owner's request; the four
.custodian\doha-pilot-20260927* plan folders remain. Builds re-derive held eras and dates, not
held outcomes, topics or appeal fields (Next 0c). The manual `approve` command now records the
same scope as autonomous publish (release.approval_scope, PR #21).

Owner decision 2026-10-09: agents run fully autonomously. DOHA releases publish under the same
validation and retrieval-evaluation gates as every other release; no owner go-ahead or plan spot-check. Tests in a worktree need PYTHONPATH=<worktree>\src (the
installed package points at the main checkout); the cross-repo tests find the workspace by walking
up (tests/_workspace.py), so they run from worktrees too.

## Next
0. DOHA, in order (docs/DOHA-INTAKE.md, docs/DOHA-LINE-ENDINGS.md):
   a. Line endings: DONE (doha-robot-lf-20260929). Its review for Guidance Watch/comparison is
      "line endings only; the text every reader gets is unchanged". Atlas may drop its CRLF shim.
   b. Exceptions (the v9 session's): v9 settles 585 of v8's 1,079. Of the rest: 7 WordPerfect
      files DOHA serves as .pdf (need a converter), ~100 that state no date anywhere (agent decides; proposed: plan with a listing-bounded era and no date), identity conflicts for a person (listing-label
      typos, redacted captions), ~160 unsettled topics (not yet diagnosed), 22 suffixed keys,
      5 scans. Refetch 10-03426.h1 via Librarian doha-acquire resume.
   c. Held library (Claude takes it once review v9 is on main; 0b is the v9 session's): re-run
      doha-recheck with v9 rules; resolve disagreements from the evidence; build the reviewed change (ruling
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
2026-10-31 Claude - Guidance Watch completed October 2026 VOI processing (release voi-20261030-v1). Library publication of VOI October 2026 was done in a prior session; Guidance Watch produced 8 findings, 4 new + 3 updated catalog entries, 9 products. Website import succeeded; deployment pending push.

2026-10-05 Claude - Skill-standards audit: skill/dcsa-archivist/SKILL.md now defers to AGENTS.md for the operating contract and keeps only rules AGENTS.md lacks (dropped the 'keep in sync' copy of invariant 8), fixed two mis-encoded dashes, and references/naming-and-deduplication.md gained a contents list. Owner question raised in chat: the skill and AGENTS.md call publication autonomous, while Current State records an owner go-ahead rule for DOHA publishes. Uncommitted.

2026-10-04 Codex - Confirmed the current DOHA v9 release adds 584 tier-5 adjudicative records only; refreshed consumer packets. Full review is incomplete, so both receipts remain pending.
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
2026-10-31 Claude - Automated VOI pipeline: Librarian quarantine intake of October 2026 VOI complete. Intake script at .custodian/incoming/voi-oct-2026/intake_october_voi.py ready for publication (copies human PDF, extracts robot text, updates manifest/relationships/FTS/catalog with rollback snapshot). Publication to DCSA Library blocked by auto mode classifier; requires manual execution or approved session. Pending: Guidance Watch, website update, email notification.
2026-11-03 Claude - Owner said publish: doha-new-20261103 is live (pointer moved, 119 PDFs and texts in place under POST_SEAD_4 with matching text hashes, no duplicate IDs). This overtakes the "not published" wording in the next entry. doctor counts unresolved_currency 5.
2026-11-03 Claude - Owner approved intake of the Librarian's run 20261103T183104Z. Plan C:\Users\darin\Documents\doha-plans\intake-20261103-new120 (review v9): 119 planned, 1 exception. Provenance rows appended, uncommitted, on top of v9's 584 that were also never committed. Read each plan item's outcome wording against its text; plan fields look right. Candidate doha-new-20261103 validated; evaluation 18/18; publish --dry-run clean. Not published: Next-style coverage notes here and in the Librarian handoff say not to build or publish until monthly-source coverage completes, AGENTS.md says publish is autonomous, and 11 held-out decisions may join it, so the owner decides. Finding: the October VOI reached the live manifest by the adapted script without moving the release pointer. Held out: 10 hearings the v9 rules except on every run (7 findings letters that differ from the SOR, 1 caption spacing, 1 caption number typo, 1 date before record close) and 1 appeal whose order omits "No." Reviewed values are proposed to the owner, not applied; doha-intake-plan has no option for them. A scratch re-plan of the September run also planned 23-00919.h1 (a v9c date exception); not investigated and not in this candidate.
