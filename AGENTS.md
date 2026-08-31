# DCSA Library Custodian project contract

This project is the maintenance plane for the adjacent DCSA Library. It does not answer FSO or compliance questions.

1. Resolve the library root from configuration or an explicit CLI argument; never hardcode a producer-specific path.
2. Run `audit` before any candidate build.
3. Production library content is read-only until an approved `publish` operation.
4. Stage all derived metadata, chunks, indexes, reports, and proposed replacements under `.custodian/releases/<release-id>/`.
5. Human artifacts may be checked only for maintenance purposes: file existence, size, format, hash, extraction quality, and parity. Never use them as answer evidence.
6. Fail candidate validation on path escape, duplicate document IDs, unclassified active content, broken parity, invalid JSON, index corruption, missing provenance, or chunks that do not occur in their robot source.
7. Do not infer currency, supersession, applicability, or binding status from filename similarity. Mark unresolved facts for review.
8. Publishing requires explicit approval, creates a rollback snapshot, and updates production pointers only after all validations pass.
9. Never delete a production source during automated publication. Quarantine or deprecate through metadata and retain rollback information.

