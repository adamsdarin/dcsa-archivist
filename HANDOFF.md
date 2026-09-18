# HANDOFF — dcsa-archivist

Last updated: 2026-09-17T12:00:26.704784+00:00 by Codex

## Current State
Archivist split implemented (2026-09-17): Library Coordinator remains at agents/conductor.md;
Evidence Reviewer owns preparation/normalization/lifecycle; Release Manager owns audits,
candidates and publication. Entry points and portable skill route to these roles. Existing
hosts keep the conductor path; delegation is host-dependent with sequential fallback.
Publish/dry-run now hold a cross-process OS lock beside the library through verification
and event emission. One active release workflow remains required. 73 tests and workspace
consistency/skill checks pass. No live library changes or production cycle run in this work.
Existing production rename/title and duplicate-selection gaps below remain unresolved.

Published release: `dd254-dec1999-lifecycle-fix-20260915` (derived_artifacts_only,
autonomous approval). Validate valid/publishable with no blockers; evaluate 16/16
(13 prior cases + 3 new DD 254 cases); post-publish doctor `integrity_healthy: true`,
`production_response_ready: true`, 0 duplicate IDs/content groups/tier conflicts,
3 unresolved-currency records, 8 verified indexes. Rollback snapshot
`.custodian/rollback/20260915T173232423413Z`. Release event emitted for
`dcsa-compare` and `fso-guidance-watch`; not acknowledged (no consumer review done).

`dcsa-forms-dd254_january_2026` is now `historical` / `historical_only`, effective
1999-12, removed from the default current-guidance index and present only in
historical research. Its source bytes, paths, title and documents.jsonl record are
unchanged. The title and filename still read "January 2026" (see Open Questions).

The release also carried, unavoidably, two source-manifest edits a 2026-09-13 Claude
FOCI cleanup session made directly to documents.jsonl (backup
`.custodian/rollback/foci-cleanup-20260913T124445Z`) whose candidate
`foci-folder-review-20260913` was built but never published or logged: removal of
`dcsa-foci-dcsa-foci-operational-guidelines` (judged fabricated, no real source) and a
dated retitle/path of `dcsa-forms-submitting_a_sponsorship_request_external`. Until
this release the published indexes still served the removed record.

Reviewed DOHA intake now builds dedicated case/topic stores in staging and binds
published indexes and metadata to integrity verification. New rebuilds route to
dcsa-library-rebuilder; regenerate remains a legacy compatibility utility.
73 tests pass. No live corpus changes made in this Codex checkpoint. Live Git state: `python ../workspace_health.py status`.

## Next
1. Preserve the earlier live-release/lifecycle decisions and unresolved label issue.
2. Process pending release events through the existing conductor/Guidance Watch.
3. Continue the shared audit; DOHA implementation is documented in docs/DOHA-INTAKE.md.

## Open Questions
- DD 254 relabel: metadata decisions cannot change `title`, and the documented naming
  remediation writes production files and manifests outside publish, which AGENTS.md
  invariant 3 forbids; renaming also breaks existing consumer citation paths. Options:
  (a) authorize a rename of the FOCI copy to the DEC 1999 name with rename_history,
  (b) authorize removal of the byte-identical FOCI copy, keeping the expired copy, or
  (c) add a reviewed title override to metadata decisions (code change).
- Tool gap: `_canonical_sort` still makes the mislabelled FOCI record canonical and the
  correctly named expired copy `excluded_duplicate`, because the ordering favours
  role priority and a shorter path over lifecycle review. Duplicate marks written by
  hand into documents.jsonl are also reset by `enrich_manifest`.

## Log
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
