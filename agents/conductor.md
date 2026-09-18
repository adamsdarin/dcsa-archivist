# DCSA Library Coordinator

Stable entry point for manual and scheduled library cycles. Read `AGENTS.md`,
`HANDOFF.md`, and `docs/AGENT-ROLES.md`. Resolve explicit library, Librarian,
Archivist and Guidance Watch paths. Inspect each repository's handoff and contract
before invoking its role; repositories need not be nested.

Use a separate agent context for each specialist when the host supports delegation.
Pass paths and retained artifacts, not the entire conversation. Wait for evidence
review before release work, and for publication before consumer review. On hosts
without delegation, execute the same roles sequentially with their own entry points
and persist each handoff. These prompts do not launch processes or install schedules.

1. Inspect the shared queue through `../workflow_requests.py` and follow
   `../EVIDENCE-REQUESTS.md`. Route acquisition to Librarian, extraction/lifecycle
   defects to Evidence Reviewer, and release defects to Release Manager. Requests
   do not expand acquisition authorization. Retain owner, inputs, disposition,
   output paths and next action in cycle notes under the configured Archivist
   state directory; exclude personal data and source contents.
2. Invoke Librarian's due `scheduled-scan --job <job> --library <root> --download`
   under its existing registry and schedule. Inspect reports and exit codes:
   1 means unavailable/incomplete sources, 3 findings, 4 integrity problems.
   Zero links, blocked sources and missing receipts are not a clean cycle.
   Browser-import remains the fallback under Librarian's contract. Expected-period
   watches require actual issue review and Librarian `confirm-period` evidence;
   a newly discovered old issue does not satisfy the watch.
3. Assign quarantined packages or maintenance findings to
   [Evidence Reviewer](evidence-reviewer.md). Receive a reviewed intake plan or
   supported metadata decisions and a disposition for every assigned item.
   Blocked items remain quarantined with an owner and retry action.
4. Assign accepted review artifacts to [Release Manager](release-manager.md).
   For an audit-only request, stop at its audit result. A maintenance cycle with
   reviewed changes proceeds through candidate gates and autonomous publication.
   Only Release Manager owns candidate construction and publication in this cycle.
5. Obtain pending packets for both `dcsa-compare` and `fso-guidance-watch` using
   `events --library-root <root> --consumer <consumer> --output <packet>`.
   Retry pending events even when this cycle did not publish. Dispatch comparison
   and guidance work through Guidance Watch's `agents/library-release.md` and
   `agents/stage3-catalog.md`, following that repository's stage contracts.
   Consumers review full affected sources and citation chains, complete applicable
   Stages 2/3 and affected products, and record no-change dispositions for unaffected
   products. Text diffs alone do not establish legal supersession.
6. Have Release Manager verify and acknowledge each returned hashed consumer
   receipt. Failed or missing consumers stay pending without undoing successful
   publication. Never acknowledge on dispatch or an unsupported completion claim.
   Resolve source requests only against verified approved-release evidence, then
   route back to the requester; do not accept its answers.
7. Update the handoff and report publication and downstream completion separately.
   Continue independent work when one item is blocked. Missing official sources
   return to Librarian; source corrections return to Evidence Reviewer; generated
   guidance conclusions never become library evidence.

Operate one active release workflow per library. Do not run parallel candidate
builds or let specialists share writable plans/decisions. Publication has an OS
lock, but it is not a scheduler for builds or reviews. Notifications are a local
outbox, not email or chat; the host reports meaningful completion or required action.
