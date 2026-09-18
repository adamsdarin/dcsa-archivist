# Archivist agent roles

The Archivist remains one repository and one release contract. Its stable cycle
entry is `agents/conductor.md`; existing schedules using that path need no change.

| Agent | Entry | Owns | Hands off |
|---|---|---|---|
| Library Coordinator | `agents/conductor.md` | Routing, retries, cycle status | Scoped inputs and artifact paths |
| Evidence Reviewer | `agents/evidence-reviewer.md` | Identity, extraction/parity, naming/taxonomy, lifecycle and duplicate review | Frozen intake plan or supported decisions; every item's disposition |
| Release Manager | `agents/release-manager.md` | Audits, candidates, gates, single publication and receipt verification | Verified release ID, reports and pending consumer events |

Librarian still owns discovery/acquisition and quarantine provenance. Guidance
Watch still owns substantive comparison and guidance products. The standalone
Rebuilder retains empty-destination reconstruction. No repository is moved.

For each assignment pass the explicit library and repository paths, requested
operation, document/package IDs, input artifact paths, output directory and known
blockers. Return the disposition (ready, unchanged, blocked, published, or pending
consumer), actual output/report paths and next owner/action. A role message is not
evidence of completion; verify its plan hashes, release checks or consumer receipt.
Use existing intake and event formats rather than inventing a second approval
system. Cycle notes are local state, not a new authoritative evidence corpus.

The coordinator invokes specialists in separate contexts where supported and
otherwise follows their prompts sequentially. Only one release workflow runs per
library, and only the coordinator edits the shared handoff during delegated work.
The publisher additionally enforces cross-process exclusion through an OS lock
beside the resolved library. On contention, retain the candidate and retry after
the other run finishes; the publisher rechecks validation, evaluation and baseline.

New intake receives normalized paths before publication. Existing production
renames/replacements remain limited by staged-tool support and must be reported
as blocked rather than performed through direct filesystem edits. This role split
does not silently resolve the DD 254 label/duplicate issues in HANDOFF.md.

The prompts define agent behavior; a shell command or event outbox does not run
a model. Existing hosts must follow the conductor and retain outputs. No new
schedules, external messages, consumer answers or library releases are created
merely by installing this structure.
