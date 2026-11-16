# HANDOFF — dcsa-archivist

Last updated: 2026-11-15 by Claude

## Current State

Uncommitted on `fix/voi-naming-rule` (2026-11-15): fixes for the gaps the October VOI rehearsal showed. Nothing was published; the live library and `.custodian` were not touched. A VOI intake is now `audit --deep` → `voi-intake-plan` → `build-candidate --deep --intake-plan` → `validate` → `evaluate` → `publish --dry-run` → `publish` → `doctor` → `events` (command lines in `docs/INTAKE-AND-EVENTS.md`). 202 tests pass. See the 2026-11-15 log entry for the decisions.

Fast release path (2026-11-15, owner instruction: fastest possible, no gate removed or weakened): `python custodian.py --config <cfg> release --library-root <lib> --release-id <id> --package <.intake.json> --out <folder> --events-output <folder>` runs the whole gated sequence in one process and stops at the first failed gate with that command's exit code; the single commands still work. Decisions: files are read and hashed on every core; an intake build stages hard links instead of a 13 GB copy and proves before sealing that it wrote nothing through them (`DCSA_STAGE_MODE=copy` restores the copy); within one process a file is read once and a result is computed once for the same bytes, a reused validation is recorded with what it was bound to (`DCSA_REREAD=1` / `release --reread` rereads at every step); `release` stops before publishing when the candidate changes a document the plan does not add. Not done: incremental chunks/indexes (25 s of a 38-minute build, and an incrementally updated SQLite index is not byte-identical to a rebuilt one). One VOI issue on a rehearsal copy of the library: about 70 minutes before, 8 minutes 12 seconds in one command on a loaded machine (`docs/INTAKE-AND-EVENTS.md`). 235 tests pass.

Current approved release is `voi-rename-20261114`, published 2026-11-14 (33,202 documents, doctor healthy, 18/18 retrieval cases). It renames the August, September and October 2026 VOIs to the collection pattern `Voice of Industry - <Month> <YYYY> Newsletter`; IDs are unchanged and nothing else moved. Its comparison and Guidance Watch event is pending (three path/title changes, no content change). The code behind it is committed on branch `fix/voi-naming-rule` (not pushed, not merged to main): `naming.py` (collection filename patterns, checked by intake and rename staging), `renames.py` and `build-candidate --rename-plan` (staged renames; publication retires the old path into the rollback only when its bytes equal the installed ones). The paragraph below is the prior release.

Prior release `doha-new-20261103`, published 2026-11-03 on the owner's go-ahead (33,202 documents, doctor healthy). It adds 119 DOHA decisions and brings the October 2026 VOI, which was in the live manifest outside any release, under a governed release. Its comparison and Guidance Watch event is pending. 11 decisions are held out pending reviewed values proposed to the owner. The paragraph below is the older state of the v9 release.

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
2026-11-14 Claude - Owner asked why three VOIs were off the naming convention and to fix it. Cause: August 2026 kept a one-off script's name through the September cleanup, and the next two reviews copied it as "the convention"; nothing checked a VOI name. Added an enforced collection pattern (src/dcsa_custodian/naming.py) and staged renames (--rename-plan), because publication could add a file but not move one and the contract forbids renaming production directly. Published voi-rename-20261114 from .custodian/incoming/voi-rename-20261114/plan.json; old files are in rollback 20261114T233039617695Z. The August metadata decision's robot path was updated in the same change. 177 tests pass. Committed on fix/voi-naming-rule (not pushed); the three pre-existing edits (two DOHA docs, one release.py line: autonomous-publication wording) went in as their own commit. Not done: a stray 261030_VOI_Newsletter.pdf in the library root, and dcsa-librarian/scripts/intake_voi.py still hardcodes the old August name (historical helper).

2026-11-15 Claude - Owner: "fix all the gaps... ensure the pipeline flows". Fixed the October VOI rehearsal's findings, uncommitted. (1) `voi-intake-plan` (src/dcsa_custodian/voi_intake.py) turns a Librarian package into robot text, parity report and plan; period from the page-1 masthead, cross-checked with publisher_claim and an optional confirm-period receipt; extractor pinned to pypdf 6.0.0 (this interpreter's). Finding: the live October text was made with pypdf 6.21.4 from the Codex runtime; under that version the new command's body is byte-identical to live, but the whole file cannot match because live's header carries a generation date and the pre-rename name, so the header now has neither. (2) Intake refuses a record without `title`. (3) Audit/doctor compare document IDs across documents.jsonl, enriched, chunks, graph and indexes: a warning plus doctor exit 2, not a blocking error, because a build is the repair. (4) The pre-staging audit no longer hashes human files (hashing adds no check; same errors gate). (5) Builds regenerate CATALOG/COLLECTIONS.json (live counts are stale for 16 collections and 5 are unlisted; the next release corrects them); DCSA_GENERAL_FTS is documented as retired. (6) Config `embedding_cache` and `embedding_cache_seed`. (7) Receipt `completed_with_gaps` is recorded as acknowledged_with_gaps and writes `<state>/acquisition-requests/<event>.<consumer>.json`. Not done: special bulletins and image-only pages still need a hand plan (the command stops); a gap acknowledgment is not reopened automatically when the document arrives.

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
2026-10-31 Claude - Automated VOI pipeline: Librarian quarantine intake of October 2026 VOI complete. Intake script at .custodian/incoming/voi-oct-2026/intake_october_voi.py ready for publication (copies human PDF, extracts robot text, updates manifest/relationships/FTS/catalog with rollback snapshot). Publication to DCSA Library blocked by auto mode classifier; requires manual execution or approved session. Pending: Guidance Watch, website update, email notification.
2026-11-03 Claude - Owner said publish: doha-new-20261103 is live (pointer moved, 119 PDFs and texts in place under POST_SEAD_4 with matching text hashes, no duplicate IDs). This overtakes the "not published" wording in the next entry. doctor counts unresolved_currency 5.
2026-11-03 Claude - Owner approved intake of the Librarian's run 20261103T183104Z. Plan C:\Users\darin\Documents\doha-plans\intake-20261103-new120 (review v9): 119 planned, 1 exception. Provenance rows appended, uncommitted, on top of v9's 584 that were also never committed. Read each plan item's outcome wording against its text; plan fields look right. Candidate doha-new-20261103 validated; evaluation 18/18; publish --dry-run clean. Not published: Next-style coverage notes here and in the Librarian handoff say not to build or publish until monthly-source coverage completes, AGENTS.md says publish is autonomous, and 11 held-out decisions may join it, so the owner decides. Finding: the October VOI reached the live manifest by the adapted script without moving the release pointer. Held out: 10 hearings the v9 rules except on every run (7 findings letters that differ from the SOR, 1 caption spacing, 1 caption number typo, 1 date before record close) and 1 appeal whose order omits "No." Reviewed values are proposed to the owner, not applied; doha-intake-plan has no option for them. A scratch re-plan of the September run also planned 23-00919.h1 (a v9c date exception); not investigated and not in this candidate.
