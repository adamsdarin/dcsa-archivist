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
necessary. The full originals remain unchanged. For a Voice of Industry issue
the `voi-intake-plan` command writes the extraction, parity report and this plan
(see "Monthly Voice of Industry intake" below); `doha-intake-plan` does the same
for DOHA runs. Other sources still need a reviewer's plan in this format.

```json
{
  "schema_version": "1.0",
  "items": [{
    "package": "source.pdf.intake.json",
    "robot_file": "source.txt",
    "robot_sha256": "<actual SHA-256 of reviewed extraction>",
    "record": {
      "document_id": "<unique edition ID>",
      "title": "<display title; required, intake refuses a record without one>",
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

## Monthly Voice of Industry intake (no hand-written JSON)

Run from this repository. `--config` is a global option and goes before the
subcommand; omit it to use `custodian.config.json`. Always pass `--library-root`.
Exit code 0 means the step passed; 2 means stop and read the error.

### Fastest sequence: one command

```powershell
python custodian.py --config "<config.json>" release --library-root "<library>" --release-id <id> --package "<quarantine run>\<source id>\261030_VOI_Newsletter.pdf.intake.json" --out "<state_directory>\incoming\voi-<YYYY-MM>-<run>" --events-output "<folder for the two consumer packets>"
```

`release` runs the same gated sequence as the ten commands below, in the same
order, in one process: `audit --deep`, `voi-intake-plan`, `build-candidate --deep
--intake-plan`, `validate`, `evaluate`, `publish --dry-run`, `publish`, `doctor`,
then `events` for `dcsa-compare` and `fso-guidance-watch`. Each step calls the
function its single command calls and has that command's exit code; the run stops
at the first step that does not exit 0, returns that code, and runs nothing after
it. Progress goes to stderr, the result to stdout, and the full record to
`<state_directory>\reports\release_<id>.json`: every step, its exit code and
seconds, the dry run's changed files, how the build was staged, and what was
reused and what it was bound to. Read that report before reporting completion.

- **With a plan already written** (any reviewed intake plan, not only a VOI issue):
  replace `--package ... --out ...` with `--intake-plan "<out>\plan.json"`. For a
  rename release use `--rename-plan "<plan.json>"`.
- **To inspect before publishing:** add `--stop-before-publish`. The run ends after
  the dry run with status `ready_to_publish` and the library untouched; finish with
  the single `publish`, `doctor` and `events` commands below.
- **Change set.** Between `evaluate` and the dry run, `release` compares
  `reports/RELEASE_CHANGES.json` with the plan. If the candidate changes any
  document the plan does not add, the run stops (exit 2) before publication:
  inspect the change report, then either publish with the single commands or
  rerun under a new release ID with `--allow-changes-outside-plan`.
- **What one process saves.** A file is read and hashed once in the run. A later
  step does not read it again while it is the same file (volume and file ID) with
  the same size and modification time; a result computed for the same bytes
  (index integrity, the release contract, a DOHA decision's era, the candidate's
  validation) is not computed again. A reused validation is returned with
  `reused` and `bound_to` (the candidate files and library files it was bound to,
  by SHA-256). `--reread` (or `DCSA_REREAD=1`) reads every file again at every
  step. The one thing reading once cannot see is a change between two steps of
  the same run that keeps a file's size and restores its modification time.
  The same rule holds inside each single command (a build no longer reads the
  DOHA texts three times); nothing is carried from one process to the next.

Measured 2026-11-15 on the 33,201-document library, adding one issue: the ten
single commands of the previous code took about 70 minutes; see `HANDOFF.md` for
the current figure for `release`.

### The same sequence as single commands

Every command still works on its own and is faster than it was (files are read
and hashed on every core; staging links instead of copying).

```powershell
python custodian.py --config "<config.json>" audit --library-root "<library>" --deep
python custodian.py --config "<config.json>" voi-intake-plan --library-root "<library>" --package "<quarantine run>\<source id>\261030_VOI_Newsletter.pdf.intake.json" --out "<state_directory>\incoming\voi-<YYYY-MM>-<run>"
python custodian.py --config "<config.json>" build-candidate --library-root "<library>" --release-id <id> --deep --intake-plan "<out>\plan.json"
python custodian.py --config "<config.json>" validate --library-root "<library>" --release-id <id>
python custodian.py --config "<config.json>" evaluate --release-id <id>
python custodian.py --config "<config.json>" publish --library-root "<library>" --release-id <id> --dry-run
python custodian.py --config "<config.json>" publish --library-root "<library>" --release-id <id>
python custodian.py --config "<config.json>" doctor --library-root "<library>"
python custodian.py --config "<config.json>" events --library-root "<library>" --consumer dcsa-compare --output "<comparison-packet.json>"
python custodian.py --config "<config.json>" events --library-root "<library>" --consumer fso-guidance-watch --output "<guidance-packet.json>"
```

`voi-intake-plan` reads the Librarian's package and, read-only, the library
manifest. It writes only `--out` (a new or empty folder outside the library): a
copy of the package and source, the robot text, `extraction-report.json` and
`plan.json`. It prints the plan path, the robot SHA-256 and the next command.

- **Package path.** Always pass the `.intake.json` explicitly; never search for
  it by name. The Librarian names downloads with underscores
  (`261030_VOI_Newsletter.pdf`), where September's was `260930 VOI Newsletter.pdf`.
- **Issue period.** Month and year come from the masthead on page 1 of the PDF,
  never from a file name. The Librarian's `publisher_claim` is cross-checked, and
  so is a `confirm-period` receipt when you pass
  `--confirm-period "<librarian state>\watch\<job>\<YYYY-MM>.json"` (it must state
  the same period and the same source SHA-256). Any disagreement stops the
  command. The plan's `lifecycle` review text lists the evidence used and says
  when no receipt was supplied.
- **Names.** The record carries `title` and paths
  `Voice of Industry - <Month> <YYYY> Newsletter`, ID `dcsa-voi-<YYYY-MM>-voi`.
- **Reproducible text.** The robot text depends only on the source bytes: the
  extractor is pinned to pypdf 6.0.0 (`pip install "pypdf==6.0.0"`; optional
  dependency group `voi`), the header has no generation date, and page locators
  are a form feed then `===== SOURCE PAGE n =====`, as the held 2026 issues use.
  Another pypdf version is refused, because it wraps table cells differently and
  would change the hash of unchanged content.
- **Parity.** A second extractor (`pdftotext`, or `--pdftotext <path>`) must find
  the same page count and at least 90% of each page's words, both ways. A page
  with no embedded text, a bulletin, or a masthead without a period stops the
  command: those need a reviewer's plan in the format above.
- **It stops when** the library already holds that issue, `--out` has content, or
  the package is not a quarantined Librarian package with matching bytes.

The dry run of a VOI intake lists the two new source files, both source
manifests, the derived manifests, chunks, graph and release indexes, the state
files, `CATALOG/COLLECTIONS.json` (regenerated from the manifest by every build)
and three directive-split `manifest.json` files (each carries a build timestamp,
so they differ on every build; their section hashes are validated).

## Configuration keys

`library_root`, `state_directory` (releases, rollback, events, reports, incoming
plans, acquisition requests; relative to this repository or absolute),
`metadata_decisions_file`, chunk sizes, and:

- `embedding_cache`: path of the embedding cache. Default
  `<state_directory>/embedding_cache.sqlite`. Vectors are keyed by model and text
  hash, so one cache serves any library. A run with its own `state_directory`
  and no cache embeds every chunk again (about 16,000).
- `embedding_cache_seed`: an existing cache to start from when the configured
  cache does not exist yet. It is opened read-only and copied once; new vectors
  go to the run's own cache. Use it for a rehearsal that must not write to the
  live state: set it to `<repository>/.custodian/embedding_cache.sqlite`.

`DCSA_EMBED_CACHE=0` still disables the cache for one run.

Environment switches for the fast path, all off by default:

- `DCSA_REREAD=1`: every step of a process reads every file again (see "Fastest
  sequence"). Same as `release --reread`, and it also applies to single commands.
- `DCSA_STAGE_MODE=copy`: stage an intake or rename build as a full byte copy of
  the library instead of hard links (see "Staging notes").
- `DCSA_HASH_WORKERS=<n>`: threads for reading and hashing; default is the core
  count, 1 is serial.
- `DCSA_CLASSIFY_PROCESSES=<n>`: worker processes for DOHA era classification;
  default is the core count for a library of 2,000 decisions or more, 0 keeps it
  in the main process. If the pool cannot start, the work is done in the main
  process and `doha_classify_pool_failed` appears in the run report.

## What the audit and doctor report

`audit` and `doctor` compare `documents.jsonl` with the published enriched
manifest, chunks, navigation graph and release indexes on the set of document
IDs. A manifest edited outside a release, or a stale derived file, appears as the
warning `derived_artifact_drift` and `derived_artifacts_agree: false`; `doctor`
then exits 2. It is a warning, not a blocking error, because the remedy is a
candidate build, which regenerates every derived artifact. `collection_catalog_drift`
means `CATALOG/COLLECTIONS.json` disagrees with the manifest; the next build
corrects it. `duplicate_relationship_rows` explains a relationship count above
the record count. `LOCAL_INDEXES/DCSA_GENERAL_FTS.sqlite` is a retired legacy
index and is not maintained: the library's own access policy records its removal
from the approved list on 2026-09-08, the release contract refuses a library
that mandates it, and its only remaining reference is the Adverse Information
Assistant's optional download-tier list (`scripts/library_paths.py`).

An intake or rename build audits the library once before staging (the gate) and
once on the staged root with `--deep` hashing. The first runs without hashing
because hashing adds no check there; the same errors stop the build either way.

## Staging notes

An intake or rename build stages a full library root under the state directory,
but no longer copies the corpus into it. Every file the change does not touch is
a hard link to the library's own file, so the staged root holds the same bytes by
construction and the `--deep` audit of it hashes the library's bytes. The files
the change rewrites are real copies: both source manifests, the new source and
robot text, and for a DOHA intake the DOHA stores it appends to. A read-only
file, or a state directory on another volume, is copied as before. The candidate
records this in `reports/STAGING.json` (`mode`, `linked`, `copied`), and before
the candidate is sealed the build checks that every linked library file still
has the size and modification time it had when it was linked; if one has changed,
the build stops and no release manifest is written. `DCSA_STAGE_MODE=copy`
restores the full copy. Budget disk space for the candidate and its indexes, not
for a second corpus. Publication is unchanged: it installs real copies from the
candidate, snapshots what it replaces into the rollback folder, and commits the
pointer last. Intake supports new additions/editions, not in-place source
replacement. Empty-root bootstrap is not implemented by this command.

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

### When the reviewed source cites documents the library does not hold

A consumer that read the whole source but could not close every citation sends
`"status": "completed_with_gaps"` and lists what is missing. It is accepted only
when `full_source_review` is true and `unheld_documents` is a non-empty list of
objects, each with non-empty `title`, `cited_at` (the locator in the reviewed
source), `needed_for` and `handling` (what the consumer did instead):

```json
{
  "status": "completed_with_gaps",
  "full_source_review": true,
  "citation_closure": false,
  "coverage_complete": false,
  "unheld_documents": [{
    "title": "<public title of the cited document>",
    "cited_at": "<locator in the reviewed source, e.g. SOURCE PAGE 4>",
    "needed_for": "<the finding or product that needs it>",
    "handling": "<e.g. wrote only what the issue itself says and marked coverage incomplete>"
  }]
}
```

(The other receipt fields are as above.) With this status `citation_closure` and
`coverage_complete` are stated true or false and at least one is false. With any
other status all three gates must be true, as before, and `unheld_documents` may
not be listed. A receipt that claims every gate true while listing unheld
documents is refused.

`ack-event` records it as `acknowledged_with_gaps`: the event leaves the pending
list, but `events` keeps showing it under `acknowledged_with_gaps` and `status`
under `consumer_acknowledgments`, each with the unheld documents. The same list
is written for the Librarian to
`<state_directory>/acquisition-requests/<event_id>.<consumer>.json`
(`status: "open"`, one entry per document). The Coordinator routes that file to
the Librarian; a request does not authorize acquisition outside its registry.

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
