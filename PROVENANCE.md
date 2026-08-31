# Provenance and open decision

Copied 2026-08-31 from `C:\Users\darin\Documents\DCSA Library\DCSA_LIBRARY_CUSTODIAN`,
where it was living **inside** the corpus it maintains. Copied, not moved — the
original is untouched and the library was mid-upload to Google Drive at the time.

Excluded: `.custodian/` (698 MB of release and report state, including the staged
candidate `initial-20260828-v7`) and `__pycache__/`. That state remains in the
library and still needs a home.

## This is not a duplicate of `src\dcsa-library-custodian`

They are two different implementations that share a name. Neither is a copy of
the other; no shared file is identical.

| | `dcsa-library-custodian` | `dcsa-library-custodian-v2` (this) |
|---|---|---|
| package | `src/library_custodian` | `src/dcsa_custodian` |
| commands | doctor, discover, browser-import | doctor, audit, build-candidate, validate, evaluate, approve, publish |
| schemas | browser-scan-page, intake-package | CITATION_CHUNK, ENRICHED_DOCUMENT, LIBRARY_STATE, METADATA_DECISIONS |
| modules | audit, cli, discovery | audit, authority, chunks, cli, common, decisions, enrich, evals, indexes, release |
| tests | test_audit, test_browser_import, test_discovery | test_custodian |
| also has | `config/source_registry.json`, `skills/` | `policies/`, `evals/`, `decisions/`, `skill/`, `MAINTAINER_START_HERE.json` |

**The important asymmetry:** `dcsa-library-custodian`'s README states *"Release
promotion is intentionally not implemented in version 0.1."* This version
implements it — `build-candidate`, `validate`, `evaluate`, `approve`, `publish`,
with approval refused unless a candidate is both structurally valid and
publishable. That is exactly the capability required to ship versioned library
releases to other people, which is the stated reason the library and the
custodian were separated in the first place.

Conversely, this version has no discovery plane: no allowlisted official-source
crawling, no browser-import, no `source_registry.json`.

They look complementary rather than competing — integrity + discovery in one,
enrichment + release in the other.

## Blocker if this becomes primary

`custodian.config.json` sets `"library_root": ".."`. This project was designed to
live one directory beneath the corpus root. Relocating it into `src` means that
value must become an explicit path or a required CLI argument — the same
`--library` pattern the other implementation already uses.

## Decision needed

Merge the two into one custodian, keep them as two projects with distinct
responsibilities, or retire one. Not a decision to make by file move.
