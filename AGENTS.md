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


<!-- HANDOFF-PROTOCOL:BEGIN -->
## Session handoff — read this first

This project is worked on by both Claude and Codex, which cannot see each
other's conversations. **`HANDOFF.md` in this directory is the shared state.**

- **At the start of a session:** read `HANDOFF.md`. Take its `Last updated`
  timestamp as a watermark and check what changed since — `git log --since=`,
  `git status --short`, and Codex session files under `~/.codex/sessions`
  newer than that watermark. Record anything you find that is not already in
  the log, then begin.
- **While working:** append a log entry after each meaningful unit of work, not
  at the end of the session. A session that runs out of context never reaches
  the end.
- **Overwrite** the `Current State` block. **Append** to the `Log`, and trim it
  to roughly 15 entries.
- Summarise decisions and the reasoning behind them. Never paste transcripts.
- Keep entries at decision level — no case detail, no personal data.

Full rules: `C:\Users\darin\src\HANDOFF-PROTOCOL.md`
Pre-restructure path translation: `C:\Users\darin\src\path-map.json`
<!-- HANDOFF-PROTOCOL:END -->
