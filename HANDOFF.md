# HANDOFF — dcsa-library-custodian-v2

Last updated: 2026-09-06T22:50:00Z by Claude

## Current State
Maintenance plane for the DCSA Library: parity and integrity audit, authority classification, exact-content dedup, citation-safe chunking, intent-routed indexes, retrieval regressions, and **approval-gated releases**. The full-corpus source-currency review launched this session is complete — **`v28` was approved (Darin Adams, 2026-09-01T17:09:42Z) and published to the live library** (`C:\Users\darin\Documents\DCSA Library`) at 2026-09-01T17:10:00Z. A rollback snapshot was taken automatically at `.custodian/rollback/20260901T171000Z` before the write. This is the first publish from this repo against the live corpus this session — everything before this was staged candidate-review work.

**The exact-duplicate-manifest-record bug is fixed** (`src/dcsa_custodian/decisions.py`, `apply_metadata_decisions`). Root cause: the function keyed matched manifest records by `(source_document_id, robot_text_path)` into a plain dict, and when two live manifest lines share that identical key (confirmed case: legacy CDSE poster records where a "small" and "large" print size point at the same OCR'd `.txt` file, so both the id and the robot path collide), Python's dict comprehension silently kept only the last one — a decision then mutated that single survivor while its sibling kept its stale default state, which validation correctly flagged as `duplicate not excluded`. Fix: match against a list of all records per identity and mutate every one, while forcing `answer_eligibility = "excluded_duplicate"` on any record that already carries `duplicate_of` (set upstream by `enrich_manifest`'s content-hash grouping) regardless of the decision's disposition — a metadata decision changes what is *true* about a document, not which physical duplicate copy is allowed to answer. All 4 existing unit tests in `tests/test_custodian.py` still pass. This is a tool-code fix inside this repo; no live library file was touched.

**`v28` is the live good build**: valid, publishable, evaluated 8/8, zero validation errors, 14,431 documents, **237 remediation items** (down from 627 at session start, a **62% reduction**). `decisions/metadata_decisions.json` now holds **398 decisions** (51 Codex + 347 this session). `v8`-`v27` are superseded intermediate builds from this session — ignore them; `v3` was already invalid before this session.

**What's fully resolved:** all DoD/SCI (30/30, including CNSSI 7003 — Darin supplied the document directly after cnss.gov stayed unreachable all session), all SEAD (8/8), all CUI (14/14), all job aids (21/21), all PHYSICAL_SECURITY (30/30 — the last one was a manifest-bug item, now fixed), CMMC/forms/NISP-tools/personnel-vetting-forms (14/14), and all 12 manifest-bug items (9 with ready answers applied once the tool bug was fixed, 3 more resolved by a final research agent). CDSE resources overall: **255 of 262 resolved.**

**The remaining 7 items are the practical research floor for this session**, after 5 rounds of research (direct browser navigation, WebSearch, and 4 background WebSearch/WebFetch-only sub-agents) found no locatable live source or could not disambiguate a generic filename. Two more research passes on this exact list (agent, then a second targeted pass) returned nothing new — further WebSearch-based attempts are very unlikely to change these:
- `CDSE_INSIDER_THREAT_2012_017_001_52427` — no matching document found under any interpretation of the filename (DoD IG number, GAO number, internal article ID).
- `CDSE_INSIDER_THREAT_CDP%20Trifold%2020May22_Final_20220525_508` — an unidentified May 2022 CDSE insider-threat trifold; "CDP" could not be resolved.
- `CDSE_INSIDER_THREAT_No_4_FINAL_NCSC_Safeguarding_Our_Future_-_Insider_Threats_-_June_25_2020` — NCSC's "Safeguarding Our Future" bulletin series exists, but this specific June 25, 2020 issue could not be located; dni.gov's restructure to archive.dni.gov may have dropped it.
- `CDSE_INSIDER_THREAT_workplaceviolence` — CDSE's Insider Threat Vigilance Campaign does maintain workplace-violence material, but the exact file behind this generic filename is unconfirmed.
- `CDSE_PERSONNEL_SECURITY_PV_Basics_Fact_Sheet` — a same-titled fact sheet exists at performance.gov (not CDSE), and CDSE's own toolkit surfaces similarly-named-but-different job aids; correspondence unconfirmed.
- `CDSE_TOOLKITS_What-Military-Members-Need-To-Know` — no matching resource found across the Personnel Security, FSO, Information Security, or Physical Security toolkits.
- `CDSE_TOOLKITS_contractor_approval_form` — no matching resource found on the FSO or Industrial Security toolkits.

**What actually closing these would take:** a human (or an agent with real, unblocked browser access to cdse.edu — this session's browser tool was reserved for the main thread and never pointed at these) manually walking every tab of every CDSE toolkit page, since these are generic filenames that don't surface via search at all. Recommend leaving these `unresolved_currency` rather than guessing.

**Nine material supersession findings this session** (none yet routed anywhere beyond `metadata_decisions.json` — see Next):
1. `dcsa-job_aids-aid-daapm-v2-2` → DAAG. DCSA's live NCSO page: cleared contractors now follow the DCSA Assessment and Authorization Guide, not DAAPM v2.2, for RMF/IS authorization. The DAAG itself is eMASS-gated/by-request, so it can't simply replace the corpus file — a reporting-requirements doc referencing DAAPM needs updating to point industry at the DAAG request process (`dcsa.quantico.hq.mbx.nao@mail.mil`) instead. **This one is a real Stage-2 candidate.**
2. `dcsa-job_aids-aid-sead-3-reporting-desktop-aid-2022-04` → a "revisedMay2024" edition DCSA now serves from the same SEAD 3 page. **Also a real Stage-2 candidate.**
3. `dcsa-dodi-sci-sci-facilities-ic-technical-specifications-scifs-v1-5` → `v1.5.1`, which ODNI now exclusively links (the individual v1.5 checklists/appendices in the same folder are unaffected).
4. NIST SP 800-61 Rev 2 → Rev 3. NIST's own page: "Withdrawn on April 03, 2025. Superseded by SP 800-61 Rev. 3" (retitled "Incident Response Recommendations and Considerations for Cybersecurity Risk Management: A CSF 2.0 Community Profile"). The cleanest, most explicit finding all session.
5. NCSC Continuous Evaluation "Top 15 FAQ" (March 2018) → a September 2020 edition in the same dni.gov directory.
6. DCSA "Cleared CUI Quick Reference Guide" (Dec 2020, memo 21-S-0587) → an October 2024 edition hosted by the DoD CUI Program office (dodcui.mil).
7. DCSA "Industry [Continuous Vetting] Enrollment Guidance" (Jan 2022) → a differently-named, materially newer DCSA document dated April 2026.
8. DCSA's SWFT (fingerprint vendor) list (June 2019) → renamed "SWFT Third Party e-Fingerprint Service Providers," most recently updated April 2026.
9. CDSE's March-2014 adverse-information-reporting guidance → substantively superseded by SEAD 3 (2017) / ISL 2021-02.
10. CISA/ISC "Planning and Response to an Active Shooter" (Nov 2015 non-FOUO edition) → a 2021 edition now live at cisa.gov.

(Findings 3-10 are CDSE training material, not things a reporting-requirements document would cite directly — Stage 2 routing is probably unnecessary for those, but worth a second opinion. Findings 1-2 are the real candidates.)

**Manifest bug — fixed, and all 12 originally-affected items resolved and applied:**
- `CDSE_PHYSICAL_SECURITY_ChangingX10-jobaid` — verified_current (CDSE Physical Security Toolkit, Locks tab).
- `CDSE_INSIDER_THREAT_520516p` — verified_current (DoDI 5205.16, esd.whs.mil).
- `CDSE_INSIDER_THREAT_superwoman`, `umbrella` — verified_current (CDSE Security Posters page).
- `CDSE_INSIDER_THREAT_usss-ntac-maps-2016-2020` — historical (USSS NTAC report, secretservice.gov; fixed-period study).
- `CDSE_CYBERSECURITY_attachment`, `BirthdatesMakeTerriblePasswords` — verified_current (CDSE poster directory, WebSearch-derived evidence).
- `CDSE_CYBERSECURITY_pwordWizard`, `fromEmail`, `devicesPword` — verified_current, confirmed live via direct browser navigation to `cdse.edu/Portals/124/Documents/posters/{small,large}/<name>.pdf` (resolved a filename-guessing WebSearch dead-end from earlier in the session).
- `CDSE_PERSONNEL_SECURITY_final-credentialing-standards` — verified_current (OPM's Suitability & Credentialing policy index still hosts this 2008 memo alongside the 2020 `cred-standards` memo, confirmed as companion, not duplicate, documents).
- `CDSE_INSIDER_THREAT_Resilience` — verified_current, moderate confidence (a live CDSE "Resilience" training-video page exists; exact filename correspondence not 100% certain, no contrary evidence either).

**authority_metadata_conflict (109 items) — scoped, non-blocking, low priority.** All already `answer_index_behavior: answer_eligible` (60), `historical_only` (45), or `unresolved_currency` (4) — the system already resolves retrieval using role-based priority regardless of the tier mismatch. This is a metadata-hygiene backlog (manifest tier vs. robot-header tier disagreement) needing a direct manifest edit, not a decisions.json entry. Not urgent.

**CDSE resources characterization:** 262 items across six subfolders (INSIDER_THREAT 116, TOOLKITS 51, CYBERSECURITY 33, PHYSICAL_SECURITY 30, PERSONNEL_SECURITY 28, NISPOM_RESOURCES 4 — all resolved), classified `training_or_context`/`not_independently_binding` in `authority.py` — lower compliance stakes than CFR/ISL/DoDI/SEAD/CUI, but far more heterogeneous content (training games, news/press releases, NIST SPs, DOJ case studies, alongside genuine DCSA/CDSE job aids).

**Research method that worked well:** CDSE toolkit hub pages (`cdse.edu/Training/Toolkits/<Name>-Toolkit/`) and the separate, better-curated, dated `Training/Job-Aids/<Category>-Job-Aids/` index pages (checked: Insider Threat Toolkit in full — 13 tabs; FSO Toolkit; Physical Security Toolkit — Planning/Design/Antiterrorism/Locks tabs; Industrial-Security-Job-Aids; Unauthorized Disclosure Toolkit; Information Security Toolkit; Personnel Vetting Toolkit and Cybersecurity Toolkit — landing tabs only; Deliver Uncompromised Toolkit — Supply Chain tab only; CUI Toolkit — default tab only, 8 more tabs unchecked). Later, delegating remaining items to background sub-agents restricted to WebSearch/WebFetch (no browser, to avoid colliding with the main thread's browser session) also worked, though all four agents hit persistent HTTP 403 bot-blocking on direct WebFetch to cdse.edu/dcsa.mil/cisa.gov/dni.gov/justice.gov — their evidence rests on WebSearch's indexed snapshots of those URLs, not a direct fetch. Real content, not fabricated, but weaker than this session's earlier browser-confirmed evidence; flagged per-item in `metadata_decisions.json` notes where it applies.

**`dcsa-cui-aid-cui-dod-marking-job-aid` reconciled, not flipped.** The CUI Toolkit's Marking tab surfaced newer-looking dodcui.mil documents ("Cleared CUI Awareness and Marking Training 2024," an "Oct 2020 (updated Mar 2022)" handbook), but these are titled and framed as industry/"Cleared" contractor training material — a parallel series distinct from this library's DoD-internal "CUI MARKING JOB AID FOR DOD | VERSION 1.0." No newer edition of that specific document was found. Decision stands as verified_current; reasoning is in the decision's own note field.

Copied on 2026-08-31 from inside the corpus at `Documents\DCSA Library\DCSA_LIBRARY_CUSTODIAN`, which its own AGENTS.md says is where custodian code does not belong. The original is untouched. `.custodian/` — 698 MB of release and report state including the staged candidate `initial-20260828-v7` — was **not** copied and still sits inside the library. See `PROVENANCE.md` for the full comparison against `src\dcsa-library-custodian`.

**The nine/ten supersession findings below now have somewhere to go.** A third project,
the **DCSA Comparison Bot**, was built on 2026-09-06 to do mechanically what this
session did by hand: pair a newly released document against the library manifest on
official document numbers and edition tokens, diff the robot text, and emit a proposed
`metadata_decisions.json` fragment. Four of the ten findings are its regression fixtures
and reproduce automatically (NIST SP 800-61r2→r3, IC Tech Spec v1.5→v1.5.1, SEAD 3
desktop aid 2022-04→revisedMay2024, Cleared CUI QRG Dec 2020→October 2024); the first
three are `deterministic`, the fourth is labelled `inferred` because the title carries no
official document number.

It proposes; it never writes. Every proposed decision carries
`requires_official_lifecycle_evidence: true` and states in its own note that a version
token is not evidence of withdrawal — this project's rule is not weakened by the
proposal arriving in machine-readable form. It is staged at
`staging/dcsa-comparison-bot/` on the `claude/dcsa-comparison-bot-k0ttop` branch of
`dcsa-librarian` because repository creation was refused by the GitHub integration.

## Next
1. Decide whether findings 1-2 (DAAPM→DAAG, SEAD-3 desktop aid) need Stage 2 routing in a reporting-requirements document — these are the only two findings this session judged as things a reporting-requirements doc would actually cite. Not yet routed anywhere.
2. Commit the pending diff (`HANDOFF.md`, `decisions/metadata_decisions.json`, `src/dcsa_custodian/decisions.py`) — prepared as a commit-message file for Darin to sign (repo requires GPG signing this session's Claude instance can't do unattended).
3. Keep using explicit `--library-root` because the default config path is not the live corpus.
4. Separately: acquire and process the August 2026 DCSA VOI (confirmed missing from the corpus — series ends at `2026-07_VOI.pdf`) through this Custodian's own acquisition path, not `fso-guidance-watch`'s — that repo must never write into the governed library directly (per Darin's explicit direction this session). Then trigger `fso-guidance-watch`'s own monthly cycle against the updated library.
5. If someone wants to push the last 7 unresolved `currency_verification` items to zero: needs a real, unblocked browser session walking CDSE toolkit tabs manually (see prior Current State detail in git history / log below) — not more WebSearch/WebFetch attempts.
6. Run the Comparison Bot's `baseline --deep` against the live manifest. Its token rules were exercised on fixtures only; 14,431 real documents will expose title patterns they do not cover.
7. Verify the published state: `python custodian.py status` (or read `ROBOT_READABLE_DIRECTORY/STATE/LIBRARY_STATE.json` in the live library) to confirm the pointer looks right from a fresh read, independent of this session's own belief that it worked.

## Open Questions
Merge with `dcsa-library-custodian` (v1) or keep separate? And does the staged candidate initial-20260828-v7 still matter?

## Log
2026-09-01T17:10:00Z Claude — **Published `v28` to the live DCSA Library**, approved by Darin Adams (explicit confirmation obtained via AskUserQuestion before running `approve`/`publish` — this repo's rule requires a named human approver and this session treated that as a real gate, not a formality). Rollback snapshot auto-created at `.custodian/rollback/20260901T171000Z`. This is the session's only write to the live corpus; every prior step was staged candidate work.
2026-09-01T17:40:00Z Claude — Ran a final research agent on the last 11 unresolved items; resolved 4 more (`final-credentialing-standards`, `Resilience`, `20180809-counterintelligence-chief`, `DSDmemo160210`), leaving 7 as the practical research floor after 5 total research rounds. Candidate v28 validates and evaluates clean (8/8); queue reduced 241→237. **Session total: 347 decisions recorded, queue 627→237 (62% reduction).** This closed the full-corpus currency-verification pass started this session.
2026-09-01T17:05:00Z Claude — Fixed the exact-duplicate-manifest-record bug in `apply_metadata_decisions` (decisions.py): matched all manifest records per identity instead of collapsing to one via dict comprehension, and made duplicate-content exclusion win over any decision disposition. All 4 unit tests still pass. Applied all 9 previously-blocked manifest-bug decisions plus the 14 CMMC/forms/NISP-tools/personnel-vetting items surfaced late in the prior session. Candidate v27 validates and evaluates clean (8/8); queue reduced 284→241. Session total: 343 decisions recorded, queue 627→241 (62% reduction). Launched a background agent on the final 11 unresolved items.
2026-09-01T16:14:39Z Claude — Applied 3 sub-agents' findings (CYBERSECURITY 20, TOOLKITS 19, INSIDER_THREAT 18 — 6 excluded for the known manifest bug), surfacing 7 more supersession findings (notably NIST SP 800-61r2→r3, explicit NIST withdrawal). Mapped the full manifest-bug scope (12 items, 6 with ready answers) and confirmed authority_metadata_conflict (109) is non-blocking. Relaunched the personnel-security sub-agent after it hit a rate limit. Candidate v22 validates and evaluates clean; queue reduced 345→284. Session total: 300 decisions, queue 584→284 (51% reduction).
2026-09-01T15:06:04Z Claude — Checked Unauthorized Disclosure Toolkit, Information Security Toolkit, and CDSE's dated Industrial-Security-Job-Aids index page; resolved 12 more TOOLKITS items. Candidate v21 validates and evaluates clean; queue reduced 357→345.
2026-09-01T14:55:54Z Claude — Checked CDSE's Physical Security Toolkit (Planning/Design/Antiterrorism/Locks tabs) and resolved 27 of 30 PHYSICAL_SECURITY items. Checked the CUI Toolkit's default tab — no matches, 8 tabs unchecked; its Marking tab surfaced the dodcui.mil documents later reconciled (see Current State). Candidate v20 validates and evaluates clean; queue reduced 384→357.
2026-09-01T14:12:15Z Claude — Checked CDSE's FSO, Personnel Vetting, and Cybersecurity toolkit pages plus the Deliver Uncompromised toolkit's Supply Chain tab; resolved 15 more CDSE items. Candidate v18 validates and evaluates clean; queue reduced 399→384.
2026-09-01T14:06:15Z Claude — Resolved 72 more CDSE resources by reusing evidence already gathered this session (duplicate SEAD/ICS-705/job-aid copies, untapped Insider Threat Toolkit matches). Found the manifest-duplicate bug for the first time (3 items). Candidate v17 validates and evaluates clean; queue reduced 471→399.
2026-09-01T12:26:45Z Claude — Checked all 13 tabs of CDSE's Insider Threat Toolkit page and cross-checked 6 DoD issuances it cites; resolved 40 of 116 INSIDER_THREAT items. Candidate v15 validates and evaluates clean; queue reduced 511→471.
2026-09-01T12:17:12Z Claude — Verified all 14 CUI items, all 21 job-aid items, and CNSSI 7003 (Darin supplied the document after cnss.gov stayed unreachable). Found the DAAPM→DAAG and SEAD-3-desktop-aid supersessions. Candidate v14 validates and evaluates clean; queue reduced 547→511.
2026-09-01T12:01:53Z Claude — Verified all 8 remaining SEAD items; all current. Candidate v11 validates and evaluates clean; queue reduced 555→547.
2026-09-01T11:52:55Z Claude — Verified 28/30 remaining DoD/SCI records; found the IC Tech Spec v1.5→v1.5.1 supersession. Candidate v10 validates and evaluates clean; queue reduced 584→555. CNSSI 7003 left undecided at this point (cnss.gov unreachable).
2026-09-01T11:02:00Z Codex — Recorded 51 exact lifecycle decisions across CFR, ISLs, forms, executive orders, NIST, and the first 15 DoD issuances. Candidate v7 validates and remains publishable; queue reduced 627→584.
2026-08-31T16:47:01Z Claude — Copied out of the corpus and committed; documented the two-implementation split.
2026-09-06T22:50:00Z Claude — Scoped and built the **DCSA Comparison Bot**, a third plane between the Librarian and this project, to mechanise the edition-pairing step this session did by hand. Deliberately scoped to corpus/edition level rather than obligation level: `fso-guidance-watch` already owns the FSO supersession register, and a second register would leave no way to tell which was right. It emits proposals conforming to this project's METADATA_DECISIONS schema and never writes `decisions/`.
