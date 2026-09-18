# Legacy library regeneration entry point

New library reconstruction belongs to
`../../dcsa-library-rebuilder/agents/rebuilder.md`, per workspace routing.
That agent is standalone and produces a one-time snapshot that is not maintained
autonomously. Read its operating contract before any rebuild.

Do not start a second regeneration workflow here. The existing `custodian.py
regenerate` command is retained as a compatibility utility for earlier reviewed
recipes and offline fixtures; its contract is in `../docs/REGENERATION.md`.
It requires the Archivist runtime, does not acquire sources itself, does not
install scheduled maintenance, and does not support DOHA reconstruction.

For maintenance of an existing governed library use `agents/conductor.md` and
normal candidate validation, evaluation and publication. Never replace an existing
library or point a consumer at a new destination implicitly.
