# DOHA robot text line endings

Status: designed 2026-09-28; implemented 2026-09-29 at the owner's direction.
Publishing still needs the owner's explicit go-ahead.

## Running it

```powershell
# Reads the library only; writes the reviewed rows once (never overwrites them).
python custodian.py doha-line-endings-plan --library-root "<library>"
python custodian.py build-candidate --library-root "<library>" --deep --release-id doha-robot-lf-YYYYMMDD
python custodian.py validate --library-root "<library>" --release-id doha-robot-lf-YYYYMMDD
python custodian.py evaluate --release-id doha-robot-lf-YYYYMMDD
python custodian.py publish --library-root "<library>" --release-id doha-robot-lf-YYYYMMDD --dry-run
```

Build with `--deep`, as the last release was, so every record's human-artifact
hash and its duplicate grouping stay as they are. The rows stay in `decisions/`
after publication; later builds find each text already LF with the reviewed
hash and count the row as applied.

## What is wrong

Release `doha-bulk-all-20260928` added 20,862 DOHA decision texts extracted by
`doha_bulk.pdftotext_extractor`, which ran `pdftotext -layout -enc UTF-8` on
Windows. Poppler's default end of line is the platform's, so every one of those
texts is CRLF. The 10,633 texts the library held before are LF.

A read-only survey of all 31,495 texts (2026-09-28) found:

- every new text is pure CRLF (no lone CR, no mixed endings); every held text is pure LF;
- no byte-order marks; every file is valid UTF-8;
- the extractor now passes `-eol unix` (test `test_extraction_writes_unix_line_ends`),
  so future extractions match the held texts on any platform.

Readers that see raw bytes, or open files with `newline=''`, see a `\r` at every
line end of the new texts. The Adjudication Atlas converter was one; it now
normalizes on read.

## Does any rule read a decision differently after the change?

No. Every Archivist reader of DOHA text opens it with `Path.read_text`, which
turns CRLF into LF: `doha_bulk.build_plan` (identity, date, era, outcome, topics,
appeal rulings), `doha_release.classify_rows` (the era and date rule candidate
validation recomputes), `doha.case_row` (loads the FTS corpus) and
`doha_quality.recheck_library`. For all 20,862 texts:

- the text those readers get is identical before and after the change;
- the rules re-run on that text reproduce the published metadata exactly:
  identity, era, decision date, outcome, topics, appeal disposition, reviewed
  outcome and appellant, with 0 differences;
- the FTS corpus `content` already equals the LF text (all 31,495 decisions),
  so the topic index needs no re-indexing;
- no two decisions share a text hash before or after, so the audit's
  duplicate-content count does not change.

Read raw with CRLF, as a byte-level consumer would, the same rules differ on two
decisions, both in topics (03-25755.h1 reads J instead of E,F,J; 05-16046.a1 reads
E instead of E,G). The published metadata follows the LF reading, and after the
change a byte-level reader agrees with it.

## What changes, and what must change together

Found by the survey and by searching the library metadata, `LOCAL_INDEXES` and
the sibling repositories for one new decision's text hash:

| Store | Change |
|---|---|
| 20,862 robot texts under `TEXT/PERSONNEL_VETTING/DOHA_DECISIONS/{PRE_SEAD_4,POST_SEAD_4}` | CRLF to LF; 420,771,503 to 413,597,260 bytes |
| `MANIFESTS/documents.jsonl` | `robot_sha256` on those 20,862 lines only |
| `LOCAL_INDEXES/DOHA_CASE_TOPICS_FTS.sqlite`, table `decisions` | `content_sha256`, `content_bytes` for those rows |
| `MANIFESTS/DOCUMENTS_ENRICHED.jsonl` | `robot_content_sha256` (the build derives it from the index) |
| Release change packet and summary | 20,862 `changed` entries, field `robot_content_sha256` (derived) |

Unchanged: the FTS `corpus` content; the DOHA era and path manifests and the path
index (they hold no hash); `DOHA_SEAD4_METADATA.sqlite`; the PDFs and provenance
rows (they hash the PDF); document IDs, paths, eras, dates, outcomes and topics;
citation chunks and vectors (DOHA decisions are not chunked); the character
counts in `intake_review.extraction` (counted on the LF text). No sibling
repository stores the text hash (Librarian, Question Bot, Atlas, Guidance Watch,
website).

History keeps the CRLF hashes and is not rewritten: the v8 intake plan, the
`doha-bulk-all-20260928` candidate and its `RELEASE_MANIFEST.json`, its rollback
snapshot and its change summary. The new release's change summary records the
transition.

## Proposed change

One candidate, for example `doha-robot-lf-YYYYMMDD`, built from the live release
without an intake plan.

1. **Reviewed input.** `decisions/doha_robot_line_endings.jsonl`, one row per text:
   `document_id`, `robot_text_path`, `rule` (`crlf_to_lf`), `before_sha256`,
   `before_bytes`, `after_sha256`, `after_bytes`, `reviewed_by`, `reviewed_utc`.
   `doha-line-endings-plan` writes it from the live library and refuses any text
   with mixed line ends (none on 2026-09-29). The rows are evidence: the build
   recomputes every value and refuses on any mismatch. The rows written on
   2026-09-29 match the independent survey hash for hash (20,862/20,862).
2. **Build** (in `doha_release`, which the Rebuilder does not vendor). For each row:
   - the live bytes must hash to `before_sha256` (fails closed if the library moved);
   - the bytes must be pure CRLF;
   - replacing CRLF with LF must give `after_sha256`;
   - `read_text` of the old and new bytes must be equal (no rule can read differently).

   Write the new bytes to `production/<robot_text_path>`. Rewrite `robot_sha256`
   on those `documents.jsonl` lines only, and copy the FTS index once to update
   `decisions.content_sha256` and `content_bytes` by primary key (no FTS5 write).
   `apply_to_records` sets `robot_content_sha256` on the enriched records, since
   `enrich_manifest` read the live index. The era patch and this patch must share
   one staged copy of each file: today `_patch_documents` and `_patch_index` start
   from the live library and would overwrite each other.
3. **Validation**, `doha_release.check_texts` (run by `validate_candidate`), for every DOHA decision:
   - the file's hash equals `documents.jsonl` `robot_sha256` where present, the
     index `content_sha256` and the enriched `robot_content_sha256`, and
     `content_bytes` equals its size;
   - no DOHA robot text contains `\r`, which stops a CRLF text being published again;
   - the corpus `content` equals the file's text.

   The existing checks still run, including the era recomputed from the staged
   LF files.
4. **Gates.** Build, validate and evaluate, which should still pass 18/18 since
   the DOHA index content is unchanged. The publish dry run must list only the
   20,862 texts, `documents.jsonl`, `DOCUMENTS_ENRICHED.jsonl`, the FTS index and
   the change summary, plus the per-release state, policy, catalog, wiki graph,
   pointer and `LOCAL_INDEXES/CUSTODIAN/<release>/` files every publication
   writes. Anything else is a stop.
5. **Owner go-ahead, then publish.** Nothing publishes on validation alone (owner
   rule for DOHA). The rollback snapshot is about 1.7 GB: texts 421 MB, FTS index
   985 MB, manifests 262 MB. The Google Drive mirror re-syncs about the same.

The code is in `doha_release.py` (`plan_line_endings`, `load_line_endings`,
`to_lf`, the build step, `check_texts`), `release.py` and `cli.py`, with tests in
`tests/test_doha_era.py` (`LineEndingTests`). Nothing in the vendored modules
(`doha.py`, `enrich.py`, `indexes.py`, `chunks.py`) changed, so the Rebuilder does
not drift. Test fixtures that wrote DOHA text with platform line endings (CRLF
on Windows) now write LF.

## Downstream effects

- **Guidance Watch and comparison.** The handoff event is actionable: 20,862
  changes, all `robot_content_sha256` only, with no chunk deltas. The release note
  should say "line endings only; the text every reader gets is unchanged" so their
  review can close in one step.
- **Question Bot carry-forward.** None of the 20,862 is `answer_eligible` (1,917
  `precedent_only`, 18,945 `exact_case_only`), so the "current evidence changed"
  rule does not fire. Only wiki answers that cite one of these decisions go back
  for research. Answers older than `doha-bulk-all-20260928` are already sent back
  by its additions, so publishing soon keeps the extra set empty.
- **Adjudication Atlas.** Its normalize-on-read stays harmless and can stay.

## Alternatives considered

- **Re-extract every PDF with the fixed extractor.** Checked for all 20,862
  published PDFs with Poppler 25.07 `-layout -enc UTF-8 -eol unix` (each PDF
  first matched its `source_sha256`): all 20,862 fresh extractions are byte for
  byte the CRLF-to-LF conversion of the published text. The two methods give the
  same bytes. Conversion is preferred because the build needs no Poppler and
  every row is checkable from the text alone.
- **Leave CRLF and have consumers normalize.** Rejected: one collection would
  carry two representations, and the published texts would differ from what the
  extractor now produces for the same PDF.
