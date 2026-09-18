# Release workflow

In the repository, Release Manager (`agents/release-manager.md`) owns this workflow.
Resolve the actual library root explicitly; the legacy relative default is not the
workspace's governed corpus.

1. `python custodian.py audit --library-root <root> --deep`
2. `python custodian.py build-candidate --library-root <root> --release-id <id> --deep`
   Add `--intake-plan <plan>` for Evidence Reviewer's frozen, hash-bound additions.
3. Review the configured state directory's candidate variance, changes, applied
   decisions and `VALIDATION.json`. Reconcile unexpected changes. Both `valid`
   and `publishable` must be true.
4. `python custodian.py validate --library-root <root> --release-id <id>` and
   `python custodian.py evaluate --release-id <id>`. Fix blockers and rebuild;
   never weaken gates to publish. Run project tests when changing release code.
5. Preview with `python custodian.py publish --library-root <root> --release-id <id> --dry-run`.
6. Publish with the same command without `--dry-run`. Passing validation and current
   retrieval evaluation automatically create approval; no extra human sign-off is
   required. `approve --release-id <id> --approved-by <name> --note <reason>` is an
   optional prior manual receipt and cannot bypass publication gates.
7. `python custodian.py doctor --library-root <root>`, verify the actual release,
   and return pending consumer events to Coordinator. A published release and
   completed downstream reviews are separate outcomes.

Publication installs staged additions and derived artifacts, snapshots replaced
files, and installs the current-release pointer last. It never automatically deletes
production sources. Existing-source renames/replacements require staged-tool support;
this workflow does not authorize direct production edits.

Publish and dry-run both hold an OS lock beside the resolved library directory,
through preflight, writes, verification and event emission. Another publisher fails
without entering preflight. The coordination file persists, but ownership ends on
process exit. Do not delete it to retry. A dry run preserves corpus bytes but may
write candidate approval/preview artifacts and the sibling coordination file.
