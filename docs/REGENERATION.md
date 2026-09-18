# Legacy Custodian recipe utility

New rebuild requests go to `../../dcsa-library-rebuilder/agents/rebuilder.md`.
The standalone Rebuilder needs neither sibling repository and carries an explicit
notice that its output is not maintained autonomously. This older command remains
for compatibility with existing reviewed recipes and tests; it is not a second
canonical agent and does not install ongoing maintenance.

Its deterministic entry point is:

```text
python custodian.py regenerate --recipe /path/to/recipe.json --destination /path/to/new-library
```

The destination must be absent or empty, or belong to an earlier attempt of the
same recipe. No personal library path is assumed. Source acquisition uses Librarian,
and full-source review uses Archivist before this command. A model-hosted run can
perform these steps in order; the Python command does not perform model judgment
or silently download websites. Install this repository's normal dependencies,
including its local embedding runtime, before building.

Recipe JSON contains schema_version "1.0", release_id, scope,
required_document_ids (a nonempty unique array), intake_plan {path, sha256}, and
evaluations {path, sha256}. Both paths are relative to the recipe directory and
must remain inside it. The intake plan uses docs/INTAKE-AND-EVENTS.md; its source
packages/extractions must match their hashes and exactly cover the required IDs.
Evaluations use evals/golden_queries.json's schema and must include a positive
check for an expected document and locator. Do not weaken evaluation cases to
get a release published. Store public recipes in Git only after privacy review;
source packages, extraction bytes and local paths stay outside Git.

The command builds the empty framework without authorizing it for retrieval, then
uses the normal candidate and gated publication code. The recipe's dedicated state
lives under the destination's .custodian/regenerator directory. Copies of reviewed
evaluations and the recipe fingerprint bind retries to the original inputs.
An interrupted incomplete candidate is preserved under failed-builds before retry.
Publication interruptions use the existing publish recovery behavior. The writer
lock prevents simultaneous regeneration attempts; it does not authorize a second
ordinary Custodian publisher against the same destination.

After success, the destination contains approved manifests, human/robot pairs,
citation chunks, retrieval indexes, robot wiki and release events. Readiness is
limited to the sources declared in scope. Exact reproduction across time requires
retained reviewed bytes and hashes; re-fetching changed websites creates a new
recipe/release. This command never clones the producer's personal corpus.

Current gap: DOHA case reconstruction is explicitly rejected until its topic and
case-index builder is portable. Empty schema-compatible DOHA indexes in a general
recipe indicate no case coverage and return no evidence; they are not a restored
DOHA library. General-source recipes are supported, full personal-corpus cloning
and universal one-command reconstruction are not claimed.
