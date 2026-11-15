# Staged intake and release handoffs

The Library Coordinator routes this workflow to Evidence Reviewer (reviewed plans)
and Release Manager (candidates, publication and receipt verification). Their
entry points and ownership are in [AGENT-ROLES.md](AGENT-ROLES.md). Existing plan
and event schemas remain the specialist handoff formats.

Librarian writes original bytes plus `<filename>.intake.json` in quarantine.
Archivist reviews them, prepares a page-located robot representation, and writes
this plan beside the package and extraction. All referenced input paths are
relative to the plan directory (the source is relative to its package); `..` and
absolute input paths are rejected. Copy packages into one staging directory if
necessary. The full originals remain unchanged.

```json
{
  "schema_version": "1.0",
  "items": [{
    "package": "source.pdf.intake.json",
    "robot_file": "source.txt",
    "robot_sha256": "<actual SHA-256 of reviewed extraction>",
    "record": {
      "document_id": "<unique edition ID>",
      "collection_id": "<existing catalog collection>",
      "domain": "<catalog domain>",
      "authority_tier": 7,
      "current_status": "current_or_verify",
      "human_source_path": "HUMAN_READABLE_DIRECTORY/<reviewed collection>/<normalized name>.pdf",
      "robot_text_path": "ROBOT_READABLE_DIRECTORY/TEXT/<reviewed collection>/<normalized name>.txt"
    },
    "review": {
      "reviewed_by": "<agent or reviewer>",
      "reviewed_utc": "<ISO timestamp>",
      "identity": "<evidence establishing source identity>",
      "provenance": "<official URL/redirect/source review>",
      "extraction": "<complete page extraction and quality checks>",
      "parity": "<original and extraction comparison>",
      "taxonomy": "<catalog path and naming-rule basis>",
      "lifecycle": "<official status evidence, or unresolved explanation>"
    }
  }]
}
```

The example tier is a placeholder, not an automatic classification. The function
checks review evidence presence and binds source/extraction hashes; only an actual
source review can establish that the evidence is true. OCR and complex tables
still require quality review. This is general intake, not a universal OCR engine.

```powershell
python custodian.py build-candidate --library-root "<library>" --release-id <id> --intake-plan "<plan.json>"
python custodian.py publish --library-root "<library>" --release-id <id> --dry-run
python custodian.py publish --library-root "<library>" --release-id <id>
python custodian.py events --library-root "<library>" --consumer dcsa-compare --output "<comparison-packet.json>"
python custodian.py events --library-root "<library>" --consumer fso-guidance-watch --output "<guidance-packet.json>"
```

Intake builds currently copy the existing corpus into temporary staging. Budget
disk space for a corpus copy plus indexes. They support new additions/editions,
not in-place source replacement. Empty-root bootstrap is not implemented by this command.

A collection with a filename pattern (`src/dcsa_custodian/naming.py`; today the
Voice of Industry) refuses an intake path that breaks it. An existing source is
renamed with a rename plan, built as its own release and staged the same way:

```json
{
  "schema_version": "1.0",
  "renames": [{
    "document_id": "<existing ID; it does not change>",
    "human_source_path": "HUMAN_READABLE_DIRECTORY/<collection>/<new name>.pdf",
    "robot_text_path": "ROBOT_READABLE_DIRECTORY/TEXT/<collection>/<new name>.txt",
    "title": "<optional new display title>",
    "review": {"reviewed_by": "<agent or reviewer>", "reviewed_utc": "<ISO timestamp>", "reason": "<naming-rule basis>"}
  }]
}
```

```powershell
python custodian.py build-candidate --library-root "<library>" --release-id <id> --rename-plan "<plan.json>"
```

Publication installs the new paths, then retires each old one into the rollback
snapshot, and only when the bytes leaving equal the bytes installed. The record
keeps its ID and gains a `rename_history` entry. A metadata decision is bound to
its record's `robot_text_path`, so update `decisions/metadata_decisions.json` in
the same change. A path shared by several records, a DOHA decision, a file-type
change and a case-only rename are refused.
The constructor still needs the existing manifests, access policies, and DOHA
router/index framework. Always supply `--library-root`; the old `..` default is
not the user's evidence corpus.

Publication emits an event only after verified pointer commit. The `events`
command reconciles a missing event after interruption. Per-library queues live
under `.custodian/events/`, with separate receipts for `dcsa-compare` and
`fso-guidance-watch`. Re-publishing the same release does not reset completion.
Older releases created before this feature report `legacy_release_without_event`;
they are not silently called processed. A first release is a baseline full review.

Packets include before/after metadata and citation chunks. Inferred edition pairs
are explicitly unverified leads. Full-source review remains mandatory, including
related authorities not represented by a textual diff. The published wiki is a
hash-bound metadata navigation graph at `ROBOT_READABLE_DIRECTORY/WIKI/GRAPH.json`;
it does not replace exact source evidence or claim to be a prose synthesis wiki.

After actual review, place this receipt beside hashed review/output artifacts:

```json
{
  "event_id": "<release ID>",
  "consumer": "fso-guidance-watch",
  "changes_sha256": "<hash from event>",
  "status": "completed",
  "reviewed_by": "<agent or reviewer>",
  "full_source_review": true,
  "citation_closure": true,
  "coverage_complete": true,
  "summary": "<findings and product dispositions>",
  "artifacts": [{"path": "review.md", "sha256": "<actual artifact hash>"}]
}
```

Use `no_relevant_change` instead of `completed` only with a documented review
explaining why. A generated packet alone is not completion.

Acknowledgment retains verified output bytes beside the event and records their
hashes in the receipt. Pending-event checks validate the receipt's gates, event
binding and retained artifact hashes each time. Damaged receipts or output files
return the event to pending work. Legacy receipts without retained artifacts are
unverifiable and also return to pending; re-acknowledge them using the original
reviewed outputs rather than inventing a new completion. Deleting an original
scratch output after acknowledgment does not lose the retained review evidence.

```powershell
python custodian.py ack-event --library-root "<library>" --consumer fso-guidance-watch --event-id <id> --receipt "<receipt.json>"
```

No process is launched merely by writing an event. Run `agents/conductor.md` in a
local scheduled agent host to close the loop. Shell discovery can run without a
model, but extraction exceptions, lifecycle review and guidance interpretation
cannot be represented as successful by an unattended shell script alone.
