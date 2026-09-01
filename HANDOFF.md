# HANDOFF — dcsa-library-custodian-v2

Last updated: 2026-09-01T11:52:55Z by Claude

## Current State
Maintenance plane for the DCSA Library: parity and integrity audit, authority classification, exact-content dedup, citation-safe chunking, intent-routed indexes, retrieval regressions, and **approval-gated releases**. Source research is in progress against the live corpus at `C:\Users\darin\Documents\DCSA Library`.

`decisions/metadata_decisions.json` now contains 80 exact-identity primary-source decisions (51 from Codex + 29 from this session, closing all but one of the 30-item DoD/SCI block). Candidate `voi-20260901-source-review-v10` is valid, publishable, and evaluated with zero errors/blockers, 14,431 documents, and 555 remediation items (down from 584). The live corpus has not been published from this candidate. `v8`/`v9` are stale/broken build attempts from this session (bad path, then an empty stub) — ignore them; `v3` was already invalid before this session.

This session verified 28 of the 30 remaining DoD/SCI records against primary sources (esd.whs.mil DoD Issuances index for the 12 DoDI/DoDM top-level records; archive.dni.gov's IC governance/regulations and ICD-list pages for ICD 705, ICS 705-01, ICS 705-02, and all 14 SCI-facility checklists) and recorded one material finding: the plain-`v1.5` copy of the IC Tech Specs for SCIF construction (`dcsa-dodi-sci-sci-facilities-ic-technical-specifications-scifs-v1-5`) is superseded by `v1.5.1`, which ODNI now exclusively links — the individual v1.5 checklists/appendices in that same folder are unaffected and remain current. **CNSSI 7003 could not be verified**: cnss.gov is unreachable from this environment (TLS cert error via WebFetch, outright connection block via browser), and per this repo's own standard ("record blocked access rather than inferring lifecycle") no decision was recorded from secondary corroboration (DCSA/CDSE both still cite the Sept 2015 version, but that is not a primary-source check). That is now the only DoD/SCI item without a decision.

Copied on 2026-08-31 from inside the corpus at `Documents\DCSA Library\DCSA_LIBRARY_CUSTODIAN`, which its own AGENTS.md says is where custodian code does not belong. The original is untouched.

`.custodian/` — 698 MB of release and report state including the staged candidate `initial-20260828-v7` — was **not** copied and still sits inside the library.

See `PROVENANCE.md` for the full comparison against `src\dcsa-library-custodian`.

## Next
1. Resolve CNSSI 7003 when cnss.gov (or another primary CNSS source) becomes reachable; do not record a decision from secondary corroboration alone.
2. Continue with SEAD (8 items — evidence already gathered this session: archive.dni.gov's SecEA Policy page and its Regulations subpage list direct PDF links for SEAD-1, 3-9, all current; SEAD-2 isn't in this library's queue), then CUI (14), DCSA job aids (21), and CDSE resources (262, by far the largest remaining bucket).
3. Keep using explicit `--library-root` because the default config path is not the live corpus.
4. After research, rebuild/validate/evaluate, obtain approval, publish the August VOI human/robot pair, then trigger FSO Guidance Watch.

## Open Questions
Merge or keep separate? And does the staged candidate initial-20260828-v7 still matter?

## Log
2026-09-01T11:52:55Z Claude — Verified 28/30 remaining DoD/SCI records against esd.whs.mil and archive.dni.gov; recorded 29 decisions (28 verified_current + 1 superseded finding on the IC Tech Spec v1.5→v1.5.1 revision). Fixed a filename-collision bug in my own first pass (wrong robot_text_path matched an existing duplicate-content record) before it reached a valid build. Candidate v10 validates and evaluates clean; queue reduced 584→555. CNSSI 7003 left undecided — cnss.gov unreachable from this environment. No live publication occurred.
2026-09-01T11:02:00Z Codex — Recorded 51 exact lifecycle decisions across CFR, ISLs, forms, executive orders, NIST, and the first 15 DoD issuances. Candidate v7 validates and remains publishable; queue reduced 627→584. No live publication or downstream FSO push occurred.
2026-08-31T16:47:01Z Claude — Copied out of the corpus and committed; documented the two-implementation split.
