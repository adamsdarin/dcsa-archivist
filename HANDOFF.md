# HANDOFF — dcsa-library-custodian-v2

Last updated: 2026-09-01T12:26:45Z by Claude

## Current State
Maintenance plane for the DCSA Library: parity and integrity audit, authority classification, exact-content dedup, citation-safe chunking, intent-routed indexes, retrieval regressions, and **approval-gated releases**. Source research is in progress against the live corpus at `C:\Users\darin\Documents\DCSA Library`.

`decisions/metadata_decisions.json` now contains 164 exact-identity primary-source decisions (51 from Codex + 113 from this session: 29 DoD/SCI, 8 SEAD, 14 CUI, 21 job aids, CNSSI 7003, and 40 of the 116 CDSE INSIDER_THREAT items). Candidate `voi-20260901-source-review-v15` is valid, publishable, and evaluated with zero errors/blockers, 14,431 documents, and 471 remediation items (down from 584 at the start of this session). The live corpus has not been published from any candidate. `v8`-`v14` are superseded intermediate builds from this session — ignore them; `v3` was already invalid before this session.

**CDSE resources is a fundamentally different bucket than everything before it, and worth reading before continuing.** It's 262 items across six subfolders (INSIDER_THREAT 116, TOOLKITS 51, CYBERSECURITY 33, PHYSICAL_SECURITY 30, PERSONNEL_SECURITY 28, NISPOM_RESOURCES 4), classified `training_or_context` / `not_independently_binding` in `authority.py` — i.e. these are training aids, not controlling authorities, so the compliance stakes of a wrong call here are much lower than for CFR/ISL/DoDI/SEAD/CUI. The content itself is also far more heterogeneous: training games, third-party news/press releases, NIST SPs, DOJ case studies, alongside genuine DCSA/CDSE job aids. CDSE's Insider Threat Toolkit page (cdse.edu) turned out to be the right hub — 13 category tabs, all checked this session, which is how 40 INSIDER_THREAT items got resolved efficiently in one pass (plus 6 DoD issuances the toolkit cited, cross-checked against esd.whs.mil). The other 76 INSIDER_THREAT items didn't match anything on that toolkit page and need a different source (possibly a separate CDSE posters/case-study library, or they're DCSA-hosted rather than CDSE-hosted). The other five subfolders each likely have their own CDSE toolkit hub page (e.g. a Physical Security Toolkit, a Personnel Security Toolkit) that hasn't been checked yet.

**CNSSI 7003 is now resolved.** cnss.gov stayed unreachable from this environment all session (TLS cert error, then an outright connection block), but Darin independently obtained the document and supplied it directly — title page confirms "CNSSI No.7003, September 2015," matching what DCSA's live NISP Tools & Resources page currently cites. Recorded verified_current.

**Two material findings from the job-aids batch, both need Stage 2/output-doc follow-up:**
1. `dcsa-job_aids-aid-daapm-v2-2` is **superseded**. DCSA's live NCSO page states cleared contractors now follow the DCSA Assessment and Authorization Guide (DAAG), not the DAAPM, to complete RMF/IS authorization. The DAAG itself is eMASS-gated / by-request-only (not publicly postable), so it can't simply replace the file in this corpus — any reporting-requirements doc referencing DAAPM v2.2 needs updating to point industry at the DAAG request process (`dcsa.quantico.hq.mbx.nao@mail.mil`) instead.
2. `dcsa-job_aids-aid-sead-3-reporting-desktop-aid-2022-04` is **superseded** by a "revisedMay2024" edition DCSA now serves from the same SEAD 3 page.

Two items in this batch (`dcsa-job_aids-aid-niss-knowledge-base`, `dcsa-job_aids-aid-sead-3-contact-reporting-exercise`) and one from the CUI batch (`dcsa-cui-aid-cui-dod-marking-job-aid`) were recorded verified_current on weaker evidence: each resolves live at DCSA's current path but isn't linked from any current hub page this session could find. Worth a second look if a stronger primary confirmation turns up.

All 8 SEAD items (SEAD-1, 3-9) and all 14 CUI items verified live and current against archive.dni.gov and DCSA's CUI Resources page respectively — no other lifecycle surprises in those two batches.

This session verified 28 of the 30 remaining DoD/SCI records against primary sources (esd.whs.mil DoD Issuances index for the 12 DoDI/DoDM top-level records; archive.dni.gov's IC governance/regulations and ICD-list pages for ICD 705, ICS 705-01, ICS 705-02, and all 14 SCI-facility checklists) and recorded one material finding: the plain-`v1.5` copy of the IC Tech Specs for SCIF construction (`dcsa-dodi-sci-sci-facilities-ic-technical-specifications-scifs-v1-5`) is superseded by `v1.5.1`, which ODNI now exclusively links — the individual v1.5 checklists/appendices in that same folder are unaffected and remain current. **CNSSI 7003 could not be verified**: cnss.gov is unreachable from this environment (TLS cert error via WebFetch, outright connection block via browser), and per this repo's own standard ("record blocked access rather than inferring lifecycle") no decision was recorded from secondary corroboration (DCSA/CDSE both still cite the Sept 2015 version, but that is not a primary-source check). That is now the only DoD/SCI item without a decision.

Copied on 2026-08-31 from inside the corpus at `Documents\DCSA Library\DCSA_LIBRARY_CUSTODIAN`, which its own AGENTS.md says is where custodian code does not belong. The original is untouched.

`.custodian/` — 698 MB of release and report state including the staged candidate `initial-20260828-v7` — was **not** copied and still sits inside the library.

See `PROVENANCE.md` for the full comparison against `src\dcsa-library-custodian`.

## Next
1. Finish CDSE_RESOURCES/INSIDER_THREAT (76 of 116 left) — try a CDSE posters/case-study library or dcsa.mil, since the Insider Threat Toolkit page is exhausted.
2. Find and work each of the other five CDSE toolkit hub pages: TOOLKITS (51), CYBERSECURITY (33, likely mostly NIST SPs — check csrc.nist.gov for bulk status rather than one at a time), PHYSICAL_SECURITY (30), PERSONNEL_SECURITY (28), NISPOM_RESOURCES (4).
3. Decide whether/how to scope the 121 duplicate_content and 109 authority_metadata_conflict items; nobody has touched those yet, and they don't require web research the way currency_verification does.
4. Route the DAAPM→DAAG and SEAD-3 desktop-aid supersession findings into Stage 2 (reporting-requirements document updates) — see Current State above.
5. Keep using explicit `--library-root` because the default config path is not the live corpus.
6. After research, rebuild/validate/evaluate, obtain approval, publish the August VOI human/robot pair, then trigger FSO Guidance Watch.

## Open Questions
Merge or keep separate? And does the staged candidate initial-20260828-v7 still matter?

## Log
2026-09-01T12:26:45Z Claude — Checked all 13 tabs of CDSE's Insider Threat Toolkit page and cross-checked 6 DoD issuances it cites against esd.whs.mil; resolved 40 of 116 CDSE_RESOURCES/INSIDER_THREAT items (39 verified_current, 1 historical — a DOJ press release used as a training case study). Candidate v15 validates and evaluates clean; queue reduced 511→471. Remaining 76 Insider Threat items, plus the other five CDSE_RESOURCES subfolders (225 items total), need a different hub page — flagged in Next.
2026-09-01T12:17:12Z Claude — Verified all 14 CUI items (DCSA CUI Resources page) and all 21 job-aid items (NISP Tools & Resources, SEAD 3 page, NISPOM Rule page), plus CNSSI 7003 (Darin supplied the document directly after cnss.gov stayed unreachable). Found two real supersessions: DAAPM v2.2 → DAAG (eMASS-gated, explicit quote from DCSA's NCSO page), and the SEAD-3 reporting desktop aid's 2022-04 edition → a May-2024 revision DCSA now serves. Candidate v14 validates and evaluates clean; queue reduced 547→511. Only CDSE resources (262) remain of the original currency_verification backlog.
2026-09-01T12:01:53Z Claude — Verified all 8 remaining SEAD items (SEAD-1, 3-9) against ODNI's official Security Executive Agent Policy page; all current, no lifecycle surprises. Candidate v11 validates and evaluates clean; queue reduced 555→547.
2026-09-01T11:52:55Z Claude — Verified 28/30 remaining DoD/SCI records against esd.whs.mil and archive.dni.gov; recorded 29 decisions (28 verified_current + 1 superseded finding on the IC Tech Spec v1.5→v1.5.1 revision). Fixed a filename-collision bug in my own first pass (wrong robot_text_path matched an existing duplicate-content record) before it reached a valid build. Candidate v10 validates and evaluates clean; queue reduced 584→555. CNSSI 7003 left undecided — cnss.gov unreachable from this environment. No live publication occurred.
2026-09-01T11:02:00Z Codex — Recorded 51 exact lifecycle decisions across CFR, ISLs, forms, executive orders, NIST, and the first 15 DoD issuances. Candidate v7 validates and remains publishable; queue reduced 627→584. No live publication or downstream FSO push occurred.
2026-08-31T16:47:01Z Claude — Copied out of the corpus and committed; documented the two-implementation split.
