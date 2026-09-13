# DCSA Library cycle conductor

Entry point for an agent host running this workspace's library cycle. Execute the
roles sequentially in this session; a scheduled shell command by itself cannot
perform the judgment steps. Resolve explicit Librarian, Archivist, Guidance Watch
and library paths. Do not assume these repositories are nested or installed.

1. Read each repository's HANDOFF and operating contract. Inspect Git state.
2. Run the due Librarian `scheduled-scan --job <job> --library <root> --download`
   locally, using its declared schedule. Inspect its exit code and scan report:
   1 means unavailable/incomplete sources, 3 findings, 4 integrity problems.
   Do not treat zero links, blocked sites, missing receipts or unavailable sources
   as a successful clean cycle. Browser-import remains the access fallback.
3. Review downloaded `.intake.json` packages. As Archivist, validate original
   source identity and provenance; extract complete robot text with page locators;
   inspect extraction/parity; apply the established naming/taxonomy framework in
   `skill/dcsa-archivist/references/naming-and-deduplication.md`. Existing collection
   paths come from the library catalog. Never invent authority or current status.
   Give a changed edition a new ID/path and preserve the prior edition. Record
   unresolved lifecycle when official evidence is absent.
4. Write the reviewed plan described in `docs/INTAKE-AND-EVENTS.md`. Review receipts
   may name the agent; no extra human approval is needed for authorized intake.
   Missing reviews remain quarantined with an explicit reason and retry action.
5. Run `build-candidate --library-root <root> --release-id <unique-id>
   --intake-plan <plan>`. This audits and builds an isolated corpus copy, includes
   source additions, indexes, chunks and the navigation wiki, and evaluates it.
   Run `publish` only when all gates pass. Publication auto-approves. Never run
   the legacy Librarian `scripts/intake_voi.py --publish` direct-writing helper.
6. Run `events --library-root <root> --consumer dcsa-compare --output <packet>`.
   This recovers a missing post-publication event and produces exact chunk diffs.
   Follow Guidance Watch's `agents/library-release.md` and `agents/stage3-catalog.md`
   for substantive comparison. Do not mark textual deltas as legal supersession.
7. Run Guidance Watch's library cycle intake, read all affected sources and their
   citation chains, complete Stages 2 and 3, and update the relevant reporting
   documents/catalog/handbook/cards. Render only products affected by the reviewed
   change. An unaffected product gets a recorded no-change disposition.
8. Acknowledge each consumer only after its review and outputs pass, with a hashed
   receipt. Failure leaves it pending for the next run. Capture blocked work in
   handoffs without source contents or personal information. Never feed generated
   conclusions back into the evidence library; send missing official sources to
   Librarian. Publish source metadata corrections only through a new release.

Operate one publisher per library at a time. Notifications here are a durable
local outbox, not email or chat messages. The hosting scheduler must invoke this
agent entry point and report meaningful completion, failures or required action.
