"""The FSO workspace folder that holds this repository's siblings, from any checkout.

A fixed parent count breaks in a worktree under .claude/worktrees, so walk up until a
folder holds the sibling repository. On GitHub Actions only this repository is
checked out, so the cross-repository tests are skipped there, visibly, instead.
"""
import os
from pathlib import Path
import unittest

MARKER = "dcsa-librarian"


def workspace_root() -> Path:
    here = Path(__file__).resolve()
    for folder in here.parents:
        if (folder / MARKER).is_dir():
            return folder
    if os.environ.get("GITHUB_ACTIONS"):
        raise unittest.SkipTest(f"needs the FSO workspace: no folder above {here} holds {MARKER}/")
    raise RuntimeError(f"no folder above {here} holds {MARKER}/; run from a checkout inside the FSO workspace")
