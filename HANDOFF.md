# HANDOFF — dcsa-library-custodian-v2

Last updated: 2026-08-31T16:47:01Z by Claude

## Current State
Maintenance plane for the DCSA Library: parity and integrity audit, authority classification, exact-content dedup, citation-safe chunking, intent-routed indexes, retrieval regressions, and **approval-gated releases**. Commit `9a6ad3c`.

Copied on 2026-08-31 from inside the corpus at `Documents\DCSA Library\DCSA_LIBRARY_CUSTODIAN`, which its own AGENTS.md says is where custodian code does not belong. The original is untouched.

`.custodian/` — 698 MB of release and report state including the staged candidate `initial-20260828-v7` — was **not** copied and still sits inside the library.

See `PROVENANCE.md` for the full comparison against `src\dcsa-library-custodian`.

## Next
1. Decide the relationship with `dcsa-library-custodian` before building on either.
2. If this becomes primary, `custodian.config.json` sets `"library_root": ".."` — it assumes it lives one level under the corpus root. That must become an explicit path or a `--library` argument.
3. Find a home for the 698 MB `.custodian/` state (reserved — waiting on the user).

## Open Questions
Merge or keep separate? And does the staged candidate initial-20260828-v7 still matter?

## Log
2026-08-31T16:47:01Z Claude — Copied out of the corpus and committed; documented the two-implementation split.
