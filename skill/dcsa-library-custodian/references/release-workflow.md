# Release workflow

1. `python custodian.py audit`
2. `python custodian.py build-candidate --release-id <id>`
3. Review `.custodian/releases/<id>/reports/VARIANCE_REPORT.md` and `VALIDATION.json`. Both `valid` and `publishable` must be true.
4. Run `python custodian.py evaluate --release-id <id>` and the project unit tests.
5. Ask the user to approve or reject the exact release ID and summarized variance.
6. After explicit approval: `python custodian.py approve --release-id <id> --approved-by <name> --note <reason>`.
7. Publish separately: `python custodian.py publish --release-id <id>`.

Publication copies only derived artifacts, places versioned indexes under `LOCAL_INDEXES/CUSTODIAN/<id>/`, snapshots replaced derived files, and atomically updates the current Custodian release pointer. It does not delete or replace human or robot source documents.

If validation fails or the candidate is not publishable, stop. Resolve the listed publication blockers; do not weaken validation or publish a partial release.
