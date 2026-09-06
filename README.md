# DCSA Archivist

This is the model-agnostic archival and release framework for the DCSA Library. The DCSA Archivist audits parity and integrity, organizes metadata, preserves provenance and lifecycle history, deduplicates exact robot content, produces citation-safe chunks, builds intent-routed indexes, runs retrieval regressions, and stages approval-gated releases. It accepts validated intake candidates from the DCSA Librarian and does not answer FSO or compliance questions.

Start with `MAINTAINER_START_HERE.json` or the portable skill at `skill/dcsa-archivist/SKILL.md`. The legacy Python package and `dcsa-custodian` command names remain stable for compatibility; they do not define the agent's role.

## Commands

```powershell
python custodian.py doctor
python custodian.py audit
python custodian.py build-candidate --release-id <id>
python custodian.py validate --release-id <id>
python custodian.py evaluate --release-id <id>
```

`approve` and `publish` are separate commands. Approval is refused unless a candidate is both structurally valid and publishable; publication also requires the explicit approval receipt.

Official-source lifecycle reviews are recorded in `decisions/metadata_decisions.json`. They are applied only to staged candidates and copied into the candidate report for provenance.

## Retrieval design

- Contractor-controlling authority is physically separated from Government issuances and guidance.
- Question intent selects eligible indexes before lexical matching.
- Historical, unresolved, duplicate, context, and DOHA precedent material cannot enter ordinary controlling-answer retrieval.
- Human paths remain unindexed citation metadata. All chunks and quotations are exact robot text with hashes and stable locators.
- DOHA retrieval continues through the dedicated topic-gated A-M case index rather than the general corpus.

## Current library observation

The initial full audit found healthy file/index integrity and complete parity relationships, but unresolved metadata remains. The latest staged candidate is intentionally not publishable because there are no verified current contractor-controlling chunks. See its variance report and remediation queue under `.custodian/releases/initial-20260828-v7/reports/`.

## Related projects

- **DCSA Librarian** — discovers official-source material and delivers validated quarantine candidates to this project.
- **DCSA Comparison Bot** — pairs a newly released document against this project's manifest, orders the two editions from official document numbers and version tokens, diffs their robot text, and emits a proposed `metadata_decisions.json` fragment for human review. It never writes into `decisions/`; applying a proposal remains this project's approval-gated job. Currently staged at `staging/dcsa-comparison-bot/` on the `claude/dcsa-comparison-bot-k0ttop` branch of `dcsa-librarian`, pending its own repository.
