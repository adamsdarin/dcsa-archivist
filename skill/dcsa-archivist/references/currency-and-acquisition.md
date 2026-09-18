# Currency and acquisition

Evidence Reviewer checks official source evidence for amendments, lifecycle and
identity. Librarian owns new downloads and quarantine packages under its registry
and existing authorization. Missing evidence routes through the shared public-source
request queue. Do not require renewed approval for work already authorized; do not
expand that authorization merely because a request contains a URL.

Check amendments to represented CFR parts, DCSA ISLs/VOI, DoD issuances and failed
official URLs as applicable. Never infer a source URL from filename patterns.
Validate source identity and complete readable extraction before proposing a
human/robot pair. Review receipts may name the agent; additional human sign-off is
not required. Release Manager publishes only through validation and evaluation gates.

Label supersession `explicit` only when an authoritative source says so; otherwise
use `inferred_pending_review`. An unavailable website does not prove absence or
rescission. Substantive interpretation belongs to Guidance Watch.

Record reviewed dispositions in `decisions/metadata_decisions.json`, keyed by both
`source_document_id` and exact `robot_text_path`. A `verified_current`, `superseded`,
or `historical` decision requires at least one HTTPS official-source evidence URL,
reviewer identity, review time and note. Candidates preserve applied decisions in
`reports/APPLIED_METADATA_DECISIONS.json`. Never use an overlay to manage DOHA
lifecycle; its dedicated case index controls it. Resolve the Archivist repository
before using these repository-relative paths from a standalone skill copy.
