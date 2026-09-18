# DCSA Archivist

This is the model-agnostic archival and release framework for the DCSA Library. The DCSA Archivist audits parity and integrity, organizes metadata, preserves provenance and lifecycle history, deduplicates exact robot content, produces citation-safe chunks, builds intent-routed indexes, runs retrieval regressions, and stages approval-gated releases. It accepts validated intake candidates from the DCSA Librarian and does not answer FSO or compliance questions.

Start with `MAINTAINER_START_HERE.json` or the portable skill at `skill/dcsa-archivist/SKILL.md`. The legacy Python package and `dcsa-custodian` command names remain stable for compatibility; they do not define the agent's role.

## Commands

For new reconstruction into an empty destination, use the standalone
`../dcsa-library-rebuilder/agents/rebuilder.md`. Its output is not maintained
autonomously. The older `custodian.py regenerate` command remains a compatibility
utility, documented in `docs/REGENERATION.md`; it is not the canonical rebuild agent.

```powershell
python custodian.py doctor
python custodian.py audit
python custodian.py build-candidate --release-id <id>
python custodian.py validate --release-id <id>
python custodian.py evaluate --release-id <id>
python custodian.py search --release-id <id> --index <index_filename> --query "<text>"
```

`approve` and `publish` are separate commands. Approval is refused unless a candidate is both structurally valid and publishable; publication creates an autonomous approval receipt after validation and current retrieval evaluation pass if no manual receipt exists.

Official-source lifecycle reviews are recorded in `decisions/metadata_decisions.json`. They are applied only to staged candidates and copied into the candidate report for provenance.

## Retrieval design

- Contractor-controlling authority is physically separated from Government issuances and guidance.
- Question intent selects eligible indexes before lexical matching.
- Historical, unresolved, duplicate, context, and DOHA precedent material cannot enter ordinary controlling-answer retrieval.
- Human paths remain unindexed citation metadata. All chunks and quotations are exact robot text with hashes and stable locators.
- DOHA retrieval continues through the dedicated topic-gated A-M case index rather than the general corpus.
- Each per-tier SQLite index carries a `vectors` table (one embedding per chunk, same eligibility/role gating as `corpus`) alongside the existing FTS5 table, so semantic search never crosses an authority-tier boundary the lexical index wouldn't also respect. Embeddings run locally (`BAAI/bge-small-en-v1.5` via `fastembed`, ONNX, CPU) â€” chunk text never leaves the machine. The release evaluation includes explicitly labeled semantic cases alongside lexical cases, using the same intent and authority gates.

## Current state

Read `HANDOFF.md` for decisions and run the read-only `doctor` for the configured library. Historical candidate observations are not current readiness evidence.

## Integrated library cycle

Start the **Library Coordinator** at `agents/conductor.md`. It assigns source
preparation and lifecycle review to **Evidence Reviewer** (`agents/evidence-reviewer.md`)
and audits, candidate builds and publication to **Release Manager**
(`agents/release-manager.md`). See [agent roles](docs/AGENT-ROLES.md) for handoffs.
Hosts with delegation use separate specialist contexts; other hosts follow the
roles sequentially. The stable conductor path preserves existing host entry points.

Staged source additions use `build-candidate --intake-plan`; successful publication
emits durable events for comparison and Guidance Watch. Publication enforces a
per-library OS lock across preflight, writes and verification, including dry runs.
The persistent lock file sits beside the library and must not be deleted while
workflows are active. See `docs/INTAKE-AND-EVENTS.md` for commands and receipts.
The published wiki is a navigation graph, not synthesized answer evidence.
