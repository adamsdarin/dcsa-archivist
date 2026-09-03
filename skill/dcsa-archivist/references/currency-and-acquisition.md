# Currency and acquisition

Use official primary sources only and obtain authorization before network access or download.

Check amendments to 32 CFR Parts 117 and 2002, DCSA ISLs, DCSA VOI issues, materially represented DoD issuances, and failed official URLs. Never infer a source URL from filename patterns.

Stage downloads under `.custodian/incoming/`. Record official URL, retrieval time, media type, size, and hash. Validate identity and readable extraction before creating a proposed human/robot pair. Publication requires human review of additions, lifecycle changes, and supersession assertions.

Label supersession `explicit` only when an authoritative source says so; otherwise use `inferred_pending_review`. An unavailable website does not prove that a document is absent or rescinded.

Record reviewed dispositions in `decisions/metadata_decisions.json`, keyed by both `source_document_id` and exact `robot_text_path`. A `verified_current`, `superseded`, or `historical` decision requires at least one HTTPS official-source evidence URL, reviewer identity, review time, and note. The candidate preserves the applied decisions in `reports/APPLIED_METADATA_DECISIONS.json`. Never use an overlay to manage DOHA lifecycle; the dedicated DOHA case index controls it.
