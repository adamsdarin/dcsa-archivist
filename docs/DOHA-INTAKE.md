# Reviewed DOHA intake

The ordinary intake plan can now include `doha_decisions` records. Every case
still needs the standard source identity, provenance, extraction, parity,
taxonomy and lifecycle review. Additionally supply the `doha_review` metadata
described in `../../dcsa-library-rebuilder/docs/DOHA-RECONSTRUCTION.md`.

Put `doha_taxonomy` in the hash-bound intake plan, or reuse the unchanged taxonomy
already in the library. Case metadata must explicitly name its review basis;
filename parsing is not evidence of outcome, applicability or currency.

`stage_intake` copies the corpus into its isolated candidate and extends the
dedicated case stores there. It validates the new records against exact robot
text, topic relationships and both path representations. Existing case IDs and
taxonomies cannot be silently replaced. Empty legacy schemas can be initialized;
nonempty incompatible schemas require a reviewed migration.

Normal candidate validation, retrieval evaluation and autonomous publication
remain required. The release change packet compares against the approved
production baseline, not the modified staging copy. Publication binds the case
indexes and robot routing metadata to the release, retains rollback information
and emits the normal comparison/guidance events. No live corpus was changed by
the synthetic implementation tests.

The legacy `regenerate` compatibility utility still excludes cases. New library
rebuilds belong to the standalone Rebuilder; this intake path maintains governed
libraries that already exist.

## Bulk intake from a Librarian acquisition run

`doha-intake-plan` turns a Librarian `doha-acquire` run into a plan this intake
accepts unchanged. It extracts each PDF with `pdftotext -layout` (the form of the
existing DOHA robot text) and derives `doha_review` from the decision text only:
case identity from the `CASENO:` header or caption, checked against the listing
label; decision date and era from `doha_era.classify`, the rule the release build
applies; outcome from the conclusion or order; topics from the `KEYWORD:` line
through the taxonomy's labels and aliases, else the formal findings. Paths and IDs
follow the library's existing DOHA convention. Any decision a rule cannot settle —
no text layer, a case number that disagrees, no established date, an ambiguous
outcome, a suffixed case key — goes to `exceptions.jsonl`, never into the plan.

```powershell
python custodian.py doha-intake-plan --run <librarian>\quarantine\doha-acquire\<run> `
  --not-held <librarian>\state\provenance\doha_not_in_library.jsonl --out <new dir> --pilot 50
```

The output holds `intake-plan.json`, `sources/`, `text/`, `exceptions.jsonl`,
`summary.json` and `doha_source_urls.additions.jsonl`. Append the additions to
`decisions/doha_source_urls.jsonl` (basis `acquisition_bytes_identical`: the
retained bytes are those fetched from that official URL) before building, then
`build-candidate --intake-plan <out>\intake-plan.json`, `validate`, `evaluate`.

Owner rule for this intake (2026-09-27): the metadata is rule-derived and signed
`doha-intake-plan rule-based review v2` (v1 before the 2026-09-27 topic fix). Do not `publish` a DOHA bulk batch until
the owner has spot-checked a sample of its plan items against their PDFs.

### Ruling types and the decision an appeal reviews (owner decision 2026-09-27)

Hearing decisions are granted or denied (`outcome` approved/denied). Appeal decisions
record what the Board did as `appeal_disposition` — affirmed, reversed or remanded —
next to `outcome`, which keeps meaning where the clearance ends up (remanded when the
case is sent back), so existing IDs, paths and consumers are unchanged. Each appeal
also carries `appealed_by` and `reviewed_decision`: the hearing decision it reviewed
(`case_key`, `decision_date`, `status` — held, in this plan, acquired, or only listed —
and the `basis` for choosing it) and what that decision had decided (`outcome`, read
from the appeal's own text). A hearing decision issued after a remand carries
`decided_on_remand_from`, the appeal that sent it back. These live in `doha_review` on
the record; exposing them in the DOHA indexes needs a reviewed schema migration, and the
library's existing appeals get them by a separate backfill over their robot text.

### Measuring accuracy, batching, and re-checking held decisions

Passing `validate` proves a candidate is consistent — hashes, eras that follow dates,
complete indexes. It cannot prove a decision labelled denied was denied, and `evaluate`
asks no DOHA questions. Accuracy is therefore measured, not assumed (`doha_quality.py`):

1. **Plan everything**: `doha-intake-plan` without `--pilot`. Read `exceptions.jsonl`.
2. **Sample and check**: `doha-accuracy-sample --plan <plan> --out <sheet.csv>` draws a
   seeded random sample in proportion to each stratum (hearing/appeal × era × ruling),
   150 scored decisions by default, plus up to 3 unscored `edge` draws for each rare
   stratum so reversed and remanded appeals are seen. The owner opens each PDF and marks
   `date_ok`, `outcome_ok`, `appeal_ok` (blank for hearings) and `topics_ok` Y or N.
   `doha-accuracy-score --sheet <sheet.csv> --target 0.05` reports the error rate and
   its one-sided 95% Clopper–Pearson upper bound, and passes only when that bound is at or
   under the target. With 150 decisions, a 5% target allows 2 wrong; 0 wrong bounds the
   rate at 2%. Edge rows are listed when wrong but never scored: over-sampling rare
   rulings would bias the estimate. A failed sheet means fix the rule and draw a new
   sample with a new `--seed`; re-scoring the same sample after tuning to it proves nothing.
3. **Re-check held decisions**: `doha-recheck --out <dir> [--not-held ...]` runs the same
   rules over the robot text of every decision the library holds and writes
   `disagreements.jsonl` (stored outcome or topics differ from the rule), `unsettled.jsonl`
   (the rule cannot decide), `ruling_backfill.jsonl` (the appeal fields and remand links
   the held decisions lack), `disagreements_sample.csv` (the owner marks each `verdict`
   `library`, `rule` or `neither`) and `existing_accuracy_sample.csv` (scored like step 2,
   measuring the held library itself). Dates are not re-checked: the build already
   recomputes them with the same rule. Nothing here writes the library; applying the
   backfill and any corrections is a separate reviewed change.
4. **Batches**: `doha-plan-batches --plan <plan> --size 5500 --out <dir>` writes
   `batch-NN` directories `stage_intake` accepts, never splitting a case, so an appeal
   and the hearing it reviewed are published together. Files are hard-linked where the
   disk allows. For each batch: `doha-append-provenance --additions <batch>\doha_source_urls.additions.jsonl`
   (refuses a conflicting row), `build-candidate --intake-plan <batch>\intake-plan.json`,
   `validate`, `evaluate`, owner spot-check, then publish.
5. **Coverage**: after the last batch, rerun the Librarian's `doha-provenance` reverse
   check; the only decision DOHA lists that the library should lack is 06-25928.h1, which
   DOHA publishes as a digest only.
