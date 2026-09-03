# Audit and remediation

Run `python custodian.py audit` first. Use `--deep` only when human-artifact hashing is required; deep mode reads artifact bytes solely for parity maintenance.

The audit checks entry points, manifest schema, path boundaries, robot and human pair existence, relationship parity, approved SQLite integrity, duplicate document IDs, duplicate robot content, authority-tier conflicts, lifecycle counts, and unresolved currency.

Classify findings as:

- **Blocking integrity:** missing robot/human pair, path escape, malformed manifest, corrupt approved index, or broken relationship metadata.
- **Release quality blocker:** duplicate ID/content, unclassified active authority, unresolved currency, conflicting authority metadata, missing locator/provenance, or failed regression.
- **Advisory:** oversized content, sparse topic coverage, or maintenance debt that does not permit a false controlling conclusion.

Do not repair production directly. `build-candidate` proposes unique IDs, canonical duplicate links, eligibility, authority roles, chunks, and separated indexes. Review the variance report before approval.

Each candidate also writes `reports/REMEDIATION_QUEUE.jsonl`. Work it in ascending numeric priority: verify currency for controlling regulations and contract clauses first, resolve authority metadata conflicts against source type and scope, then confirm canonical records for exact-content duplicates. An item remains excluded from answer indexes until its required resolution is supported by recorded evidence. Do not clear a finding merely to make a release publishable.
