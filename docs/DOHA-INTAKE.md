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
accepts unchanged. It extracts each PDF with Poppler's `pdftotext -layout -eol unix`
(the form of the existing DOHA robot text; before 2026-09-28 it omitted `-eol unix`,
so the 20,862 texts of `doha-bulk-all-20260928` are CRLF, see DOHA-LINE-ENDINGS.md)
and derives `doha_review` from the decision text only:
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
`doha-intake-plan rule-based review v9` (v1 before the 2026-09-27 topic fix; v2 before hearing outcomes were cross-checked; v3 misread older layouts; v4 took topics from one source only; v5 failed its accuracy sample; v6 read guideline names and the decision's own date line; v7 fixed appeal links and double postings; v8 drops guidelines the decision says were not alleged; v9 reads the caption and header variants, 1996-97 opening date lines, later and earlier Board order wordings and summary dispositions found among v8's exceptions, see "Review v9" below). Do not `publish` a DOHA bulk batch until
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

Since review v7 (2026-09-28) neither link ever points at a decision dated on or after the
one linking to it. DOHA does not list every first hearing decision, so a case's only
listed hearing decision is often the one issued on remand, after the appeal; that appeal's
`reviewed_decision` is "not identified" (with the reason), and a remand decision is never
linked to an appeal decided after it. The v6 plan had 60 such links.

### Decisions DOHA posts twice

DOHA posts some hearing decisions twice, as h1 and h2, from different files of one text.
Since review v7 a decision whose words match another decision of the same case, type and
stated date (planned earlier or already held) to at least 0.95 is an exception naming its
twin, so the library keeps one copy. The v6 plan held 8 such pairs, all at 0.997 or more;
the closest genuinely different same-day pair reached 0.83.

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

### What a decision's topics are (owner decision 2026-09-27)

Topics are every guideline the case put in issue — all the guidelines the SOR alleged —
not only those DOHA's `KEYWORD:` line lists. The rule takes the union of the KEYWORD
line, the formal findings and the guidelines the Statement of the Case says were
alleged, and records which sources contributed. Only when none names a guideline is the
whole text read. A guideline added by an SOR amendment counts, and so does one alleged
and later withdrawn (owner ruling on the v5 sample, 2026-09-27).

Since review v6 (after the v5 accuracy sample failed on topics, 3 of 150) the formal
findings and the Statement of the Case are also read when they name a guideline by title
only ("Paragraph 1, Financial Considerations: AGAINST APPLICANT", "under the financial
considerations guideline"), using formal names, never the taxonomy's search aliases; and
every guideline the decision rules on ("Guideline F is found for applicant") is added.
Topics are part of the document ID and file name, so a decision whose topics cannot be
settled is an exception, never planned: nothing names a guideline, or the formal findings
name a letter that nothing else in the decision names while the Statement of the Case
alleges others (a judge's typo, "Paragraph 1. Guideline F" where paragraph 1 is criminal
conduct).

Since review v8 (2026-09-28, owner decision to close the gap before the combined build) a
guideline the decision says is not part of the case is no topic, however often it is mentioned:
"Guideline C is not alleged", "the SOR did not cite Guideline H", "a Guideline E allegation that
was not listed in the SOR", "should have been alleged under Guideline E", "Guidelines F and J,
which are not at issue in this case" (a denial covers the rest of its list, "under Guideline D
or Guideline J"). A sentence about the SOR outweighs such a denial ("The SOR was based on
Guideline E and Guideline J"), as does an amendment adding the guideline; "not at issue on
appeal" means alleged and not appealed. Remarks about other cases ("this program has
adjudicated Guideline B and C cases") count for nothing, and the judge's first-person "I" after
a guideline ("Under Guideline E, I conclude") is not Guideline I. Against the v7 plan this
removed a letter from 30 decisions, each read and confirmed, and added none; it includes the
two known errors (15-00207.h1 in the batch 4 spot-check, 15-02326.a1 in the v6 sample).

### Which date is a decision's date (owner decision 2026-09-27)

The decision's own date line wins: its `DATE: March 20, 2019` line, else the caption date
line above "Decision". DOHA's numeric index header (`DATE: 03/20/2019`, beside the
`KEYWORD`/`CASENO` lines DOHA prepends) is used only when the decision states no usable
date of its own. The two disagree in 35 of the 4,300 planned decisions carrying both and
12 held ones, usually by a day or a mistyped year; none changes era. The rule lives in
`doha_era`, which the release build applies to every held decision, so the next
candidate corrects those 12 held dates too.

### Review v9 (2026-09-29): reading what v8 held back

v9 was written from samples of v8's 1,079 exceptions. Each change reads a wording v8 did
not, and is measured against v8 on the same texts (every published and held decision):

- Identity: captions with en/em or doubled dashes, "ISCR Case:", "ISCR No.", the "ICSR"
  typo, "CR" where extraction lost "IS", CAC, a footnote digit ("ADP1 Case No."), and
  DOHA's CASENO header run into the line before or without its colon. A one-character
  typo in the CASENO header is accepted only when the caption names the listed case
  exactly. A number is still accepted only when it is the listed case's, so a cited case
  can never become an identity.
- Date: the 1996-97 layouts' date line above "Appearances" ("November 7, 1996",
  "Date: _August 22, 1997_"), used only when no caption date line exists. It changes no
  published or held date.
- Hearing outcomes: "consistent with national interest" without "the", "interests", "a
  position of trust is granted", and the 2016-17 summary dispositions ("he met his
  ultimate burden of persuasion ... This case is decided for Applicant"). "whether it is
  clearly consistent" (the question a hearing decides) and 10 U.S.C. 986's "unless a
  waiver is granted" are boilerplate, not outcomes.
- Board orders: "The decision in ISCR Case No. ... is AFFIRMED", "The decision of the
  Judge is ...", "The judgment of the Administrative Judge granting ... is ...", "The
  case is REMANDED", "the Board reverses the Administrative Judge's favorable ...". The
  appellant is also named by the appellate burden ("Applicant has failed to meet his
  burden on appeal of demonstrating error"), never by the merits burden of persuasion.

Against v8, v9 reads no held decision differently where v8 read it at all (it only reads
more). Of the 20,862 published decisions it reads four differently, each a finding for the
held-library review rather than a regression: 04-11414.a1 (its digest says a favorable
decision was remanded, its Order that the judgment denying a clearance was), 08-07803.h1
and 10-03757.h1 (each contradicts itself), and 06-20964.a1 (the Order names Department
Counsel's burden, so the appellant is corrected).
