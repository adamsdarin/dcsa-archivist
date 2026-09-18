# Human-readable naming and deduplication

Evidence Reviewer owns normalization proposals. New intake uses normalized paths
in its reviewed plan and Release Manager installs them through staged publication.
The historical remediation notes below describe pitfalls, not permission to edit
production directly. Existing-file renames/replacements unsupported by release
tooling remain explicit tooling blockers with proposed old/new paths and required
reference updates. AGENTS.md's publication-only invariant takes precedence.

This reference exists because every rule below was learned the hard way in one long session
(2026-09-03, see `HANDOFF.md` for the full narrative) and would otherwise only live in that
transcript. Read this before touching `HUMAN_READABLE_DIRECTORY` filenames or resolving
duplicates.

## Naming convention

**Tier 1 (mechanical, apply broadly, no research needed):** lowercase the extension; collapse
whitespace to `_`; strip `(`, `)`, and `,` characters (keep the words, drop the punctuation);
normalize a loose `M-D-YYYY` date token to `YYYY-MM-DD`; collapse repeated `_`/`-` runs; strip
a leading prefix that only repeats the folder's own category (e.g. `FORM_` inside `.../FORMS/`,
`CUI_` inside `.../CUI/` — verify the pattern per-folder, don't assume it generalizes). Do not
touch hyphens inside an existing token (`sf-328`, `15CFR300-744`) and do not rewrite wording.

**Tier 2 (structured, requires reading the actual document):** for authoritative numbered
issuances — DoDI/DoDM/DoDD, Executive Orders, CFR parts, ICD — the target shape is
`{TYPE}_{NUMBER}[_V{n}]_{Title}_{Date}.pdf`, `TYPE` in caps (`DODI`, `DODM`, `DODD`, `EO`,
`CFR`, `ICD`). Never trust a filename, a synthetic header, or memory for the title/date —
read the source PDF or robot text directly. When a document was amended in place (same
number, "Incorporating Change N"), use the *latest* change/effective date, not the original
issue date. A document actually *superseded* by a different issuance is a different situation
from an in-place amendment — flag it rather than dating it as current; this repo has no
superseded-marker convention yet, that's still open. Always preserve the pre-rename path in a
`rename_history` list field on the manifest record
(`{previous_human_source_path, previous_robot_text_path, renamed_utc, renamed_by}`) so a future
re-scrape can still match the document against its old name.

## Duplicate resolution

The default per skill invariant 10 is **quarantine, never auto-delete**: mark the non-canonical
record `duplicate_of`/`canonical_document_id` pointing at the canonical one, set
`answer_eligibility: excluded_duplicate`, leave the file in place. `enrich_manifest`
(`src/dcsa_custodian/enrich.py`) already does this automatically at `build-candidate --deep`
time, grouping by `human_artifact_sha256` (the real source-file hash) when available, falling
back to `robot_content_sha256` otherwise — this was a real bug until 2026-09-03 (it used to
group DOHA records by a SQLite side-table hash that had no relationship to the actual file,
missing ~2,756 duplicates). `_canonical_sort`'s tie-break prefers, in order: higher
authority_priority, `answer_eligible` status, non-`LEGACY` path, a record with `rename_history`
present (a deliberately curated name should win over an untouched raw one), shorter path,
then casefold — check this order still makes sense before trusting an automatic pick.

Actual deletion happened this session only via explicit, scoped, per-case human authorization
(never a blanket default) — DOHA case pairs with fabricated placeholder metadata, and library-
wide confirmed byte-identical pairs — always backed up first. Don't delete without that same
explicit authorization.

## Known gotchas

- **Windows/NTFS path resolution is case-insensitive.** `os.path.exists()` or hashing two
  differently-cased path strings for what looks like "two files" can silently resolve to the
  *same* file — this caused a real near-miss (a file briefly deleted, caught and restored from
  backup). Confirm two entries actually exist as distinct case-sensitive names via a directory
  listing before concluding "duplicate"; a same-name-different-case rename needs a two-step
  rename through a temp filename, since Windows treats the direct form as a no-op/conflict.
- **Orphan files exist**: a physical PDF + robot `.txt` pair with *no* manifest record at all
  (found several: `DoDM_1000.13`, plus EAR/ITAR/a duplicate CUI file in `AUTHORITIES/CFR`).
  Do not fabricate a manifest record. Route acquisition/provenance recovery to
  Librarian, then let Evidence Reviewer prepare reviewed intake for staged release.
  Leave production untouched until that workflow supports the proposed change.
- **`machine_text_exists: true` does not mean the text is right.** Found both a broken scrape
  (a GovInfo "Page Not Found" page saved as the extraction) and actively wrong content (an
  unrelated SEC filing saved under an Executive Order's record). Read the source PDF directly
  (the `Read` tool handles PDFs) before assuming content is unrecoverable or trusting it as a
  title/date source.
- **The synthetic `AUTHORITY HEADER` block can be stale.** Its `EFFECTIVE` field sometimes
  reflects the original issuance date, not a later amendment already described elsewhere in
  the same document's body. Grep the full raw text for `Change N ... Effective` before trusting
  the header.
- **Some duplicates are false positives by design**: one large compiled source PDF (e.g. a
  full DFARS text) can legitimately back many separate per-clause manifest records that all
  hash-match on `human_source_path`. Don't collapse these.
- **Three files must move together.** `documents.jsonl`, `ROBOT_READABLE_DIRECTORY/MANIFESTS/
  relationships.jsonl`, and `decisions/metadata_decisions.json` (this repo, not the library)
  all reference paths by record. A rename or deletion that updates only `documents.jsonl`
  leaves the other two stale, which `audit`/`build-candidate` will catch
  (`broken_relationship_metadata`, "metadata decision does not match a manifest record") — but
  only if you run them. Update all three in the same pass, every time.
- **Back up before every write**, to `.custodian/rollback/<label>-<timestamp>/`, mirroring the
  library's relative paths — same pattern `publish_candidate` already uses. Verify after
  (`size_before == size_after` for a rename; re-run `doctor`/`build-candidate --deep`) rather
  than trusting a script's exit code alone.

## Status

See `HANDOFF.md` for exactly which folders have had the full Tier 2 treatment, which have had
Tier 1 only, and which are untouched — that changes session to session and belongs in the log,
not duplicated here.
