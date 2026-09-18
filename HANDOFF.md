# HANDOFF — dcsa-archivist

Last updated: 2026-09-18 by Claude

## Current State
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
1. Guidance Watch and comparison still owe reviews for three release events
   (nist-172-r3-intake-20260911, dd254-dec1999-lifecycle-fix-20260915,
   dd254-canonical-title-20260918); acknowledge only with their hashed receipts.
2. When the Librarian's ledger has verified provenance rows, run import-provenance,
   then build/validate/evaluate/publish. That is how the Rebuilder's 749
   retained-bytes-only records gain official URLs.
3. Continue the shared audit; DOHA implementation is in docs/DOHA-INTAKE.md.

## Open Questions
None open. The DD 254 relabel question (options a/b/c) was resolved on 2026-09-18
with option (c) plus a reviewed canonical choice, at the owner's direction.

## Log
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
