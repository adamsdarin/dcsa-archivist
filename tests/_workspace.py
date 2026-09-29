"""The FSO workspace folder that holds this repository's siblings, from any checkout.

A fixed parent count breaks in a worktree under .claude/worktrees, so walk up until a
folder holds the sibling repository.
"""
from pathlib import Path

MARKER = "dcsa-librarian"


def workspace_root() -> Path:
    here = Path(__file__).resolve()
    for folder in here.parents:
        if (folder / MARKER).is_dir():
            return folder
    raise RuntimeError(f"no folder above {here} holds {MARKER}/; run from a checkout inside the FSO workspace")
