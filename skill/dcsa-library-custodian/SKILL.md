---
name: dcsa-library-custodian
description: Audit, organize, deduplicate, enrich, chunk, index, validate, stage, and publish approved releases of a local DCSA retrieval library. Use for library currency, parity, metadata, retrieval-quality, or release maintenance; do not use to answer substantive FSO or compliance questions.
---

# DCSA Library Custodian

Maintain the DCSA Library as a trustworthy, portable retrieval dataset. This skill is the maintenance plane; it does not answer questions from the corpus.

## Invariants

1. Resolve the library root from `custodian.config.json` or an explicit user-confirmed path. Never hardcode a producer path.
2. Run `python custodian.py audit` before proposing or building changes.
3. Production is read-only by default. Build all proposed artifacts under `.custodian/releases/<release-id>/`.
4. Consumer bots remain robot-only. Custodian access to human artifacts is limited to maintenance: existence, format, hash, approved extraction, and parity. Never use human content as answer evidence.
5. Treat currency, supersession, applicability, and contractor binding as explicit metadata. Do not infer them from filenames or similarity.
6. Exclude duplicates, unresolved currency, unclassified active content, historical material, and broken parity from default answer indexes.
7. Use authority/lifecycle gates before lexical or semantic relevance. Guidance cannot independently create an obligation.
8. Keep `human_source_path` unindexed and citation-only. Chunks and quotations come exclusively from robot content.
9. Publishing requires a valid and publishable candidate, regression pass, explicit approval receipt, and rollback snapshot. Structural validity is not publication readiness. Never self-approve a release.
10. Never delete production source artifacts automatically.

## Modes

- For health, parity, duplicates, metadata conflicts, or index integrity, run `audit`; read [references/audit-and-remediation.md](references/audit-and-remediation.md).
- For a proposed metadata/chunk/index refresh, run `build-candidate`, then `validate`; read [references/release-workflow.md](references/release-workflow.md).
- For official currency checks or acquisition, read [references/currency-and-acquisition.md](references/currency-and-acquisition.md) and obtain network/download approval first.
- For authority roles, answer eligibility, and consumer retrieval policy, read [references/authority-and-retrieval.md](references/authority-and-retrieval.md).

Use the project-local Python runtime command shape:

```powershell
python custodian.py <command>
```

Report candidate findings and unresolved records before requesting approval. `approve` records the user's decision; `publish` is a separate operation.
