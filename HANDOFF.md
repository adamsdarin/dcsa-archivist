# HANDOFF — dcsa-archivist

Last updated: 2026-09-11T23:40:00+00:00 by Claude

## Current State
Enrichment/release plane. Reviewed, hash-bound staged source intake via `build-candidate
--intake-plan`, a published hash-bound robot navigation graph, and durable per-library release
events with separate comparison/Guidance Watch receipts. 52 offline tests pass.

**A live source-intake publication has now occurred** — this supersedes the prior "no live
source/release mutation" state. Release `nist-172-r3-intake-20260911` published NIST SP 800-172
Rev 3 and 800-172A Rev 3 through the intake path: the first non-derived publication, scope
`source_intake_and_derived`. Live doctor reports `integrity_healthy: true`,
`production_response_ready: true`, 0 duplicate IDs, 0 content-duplicate groups, 0 tier conflicts,
3 unresolved-currency records, 8 verified indexes. Rollback snapshot at
`.custodian/rollback/20260911T232458779996Z`.

Live Git state: run `python ../workspace_health.py status`; prior details are in `HANDOFF-archive.md`.

## Next
1. Deploy agents/conductor.md in a local agent host to process quarantine and pending events; an event does not launch a model.
2. Read docs/INTAKE-AND-EVENTS.md; rebuild older candidates for new wiki/event artifacts. Source intake currently stages a full corpus copy and requires existing framework files.
3. Portable empty-root regenerator remains a proposed build-recipe/CLI project; see ../PROCESS-MAP.md. Changes remain uncommitted alongside prior work.

## Open Questions
No new decision needed for the authorized implementation. Prior source-acquisition
and migration questions remain scoped separately as noted above.

## Log
2026-09-11 Claude — Ingested and published NIST SP 800-172 Rev 3 + 800-172A Rev 3 via the new
intake path (release `nist-172-r3-intake-20260911`). Both prior editions were withdrawn
2026-05-13; Codex's own 2026-09-01 decision had said "acquire Rev. 3 separately" and it had never
happened — the `superseded_without_successor` lint check rediscovered it independently, which is
the first time that layer paid for itself. Used `stage_intake` rather than hand-editing manifests:
checked repo state first and found Codex had built exactly the path I was about to improvise.
Deliberate departure from sibling convention: extracted **page-located** robot text (form-feed
separators), so these two cite as `page:49;chars:0-2160` while older NIST files still cite as
`block:1;chars:296580-301348` into a 1.6M-character blob. Chunks landed page-aligned, 119 and 124.
No `metadata_decisions.json` entries added — the hash-bound `intake_review`/`intake_provenance`
blocks are stronger evidence than a decision row, and a second identity-matching surface would add
risk for no gain; revisit if sibling consistency matters more than that. Validate clean, evaluate
13/13, dry-run reviewed before publishing, rollback snapshot taken. Lint 10 -> 8 findings: both
NIST supersession gaps closed. 243 Rev 3 chunks are in `DCSA_CURRENT_GUIDANCE_CHUNKS_FTS` which is
default-allowed, so enhanced-CUI questions are answerable for the first time; the withdrawn
editions correctly sit in historical-research, off the default path. Consumer packets written to
the release `reports/` at `status: review_required` — not acked, since acking would falsely assert
a review happened. Note for whoever reads the packets: the edition pair is labelled
`unverified_issuance_family_lead`, which is the `confidence: derived` guardrail on graph edges
surfacing correctly downstream — treat it as a lead, not a fact.

2026-09-11 Codex — Completed cross-system role/handoff implementation and process map. Tests: 65 Librarian, 52 Archivist; three cross-system acceptance cases and shared-policy checks pass. No live publication, acquisition, scheduling, or guidance product changes. Portable regenerator assessed as a proposed recipe-driven CLI, not implemented.
2026-09-11 Codex — Cross-system workflow audit in progress. User selected Librarian -> Archivist -> approved release -> comparison and Guidance Watch. Implementing staged source intake, published navigation graph, and durable release packets with completion receipts. Existing dirty files preserved. No live library changes; installed Windows task inspection found no DCSA/FSO/Custodian-named tasks.
2026-09-10 Codex — Completed authorized implementation. 47 tests pass, including three offline cross-system acceptance cases. Expanded staged-release evaluation passes 13/13 with a real local semantic query. Publication re-runs current evaluations so older reports cannot bypass new cases. Changes remain uncommitted, including preserved prior edits.
2026-09-10 Codex — Implementing the five authorized workspace improvements and accepted-answer wiki. Preserved the entire prior handoff in the archive, including pre-existing edits. Validation is in progress; do not interpret implementation as a live library release.
