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
