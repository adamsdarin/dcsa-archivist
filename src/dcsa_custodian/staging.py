"""Stage a coherent library root for an isolated build without copying the corpus.

An intake or rename build needs a root that looks like the library plus the reviewed
change. Copying 13 GB to add one document is a large part of that build's wall time.
Here every file the change does not touch is a hard link to the library's own file, so
the staged root holds the same bytes by construction, and only the files the change
rewrites are real copies. Nothing is written through a link:

- a file named in ``copy`` (the manifests an intake rewrites, the DOHA stores a DOHA
  intake appends to in place) is always a real copy;
- a read-only file is copied, because removing a read-only link would mean clearing the
  attribute on the library's own file;
- where a link cannot be made (another volume, a filesystem without links) the file is
  copied, as before;
- ``verify_untouched`` then proves it: the size and modification time of every linked
  library file are compared with what they were when the link was made, before the
  candidate is sealed.

``DCSA_STAGE_MODE=copy`` restores the full byte copy.
"""
from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path
from typing import Any, Iterable

from .common import map_ordered, norm

IGNORED = (".custodian", "OPERATIONS", ".git")


def _walk(root: Path, ignored: tuple[str, ...] = IGNORED) -> tuple[list[str], list[str]]:
    """Folders (parents first) and files under ``root``, skipping ``ignored`` names at every level."""
    folders: list[str] = []
    files: list[str] = []
    pending = [""]
    while pending:
        relative = pending.pop()
        with os.scandir(root / relative if relative else root) as entries:
            for entry in sorted(entries, key=lambda item: item.name):
                if entry.name in ignored:
                    continue
                child = f"{relative}/{entry.name}" if relative else entry.name
                if entry.is_dir():
                    folders.append(child)
                    pending.append(child)
                else:
                    files.append(child)
    return folders, files


def _signature(path: Path) -> tuple[int, int]:
    # os.stat opens the file: a directory listing can be stale for a file with several links.
    status = os.stat(path)
    return status.st_size, status.st_mtime_ns


def stage_tree(root: Path, destination: Path, copy: Iterable[str] = ()) -> dict[str, Any]:
    """Make ``destination`` a staged library root: links for unchanged files, copies for ``copy``."""
    root = root.resolve()
    if os.environ.get("DCSA_STAGE_MODE", "link").strip().lower() == "copy":
        shutil.copytree(root, destination, ignore=shutil.ignore_patterns(*IGNORED))
        return {"mode": "copy", "linked": 0, "copied": None, "unlinkable": 0, "guard": {}}
    real = {norm(relative).casefold() for relative in copy}
    folders, files = _walk(root)
    destination.mkdir(parents=True)
    for relative in folders:
        (destination / relative).mkdir()

    def place(relative: str) -> tuple[str, tuple[int, int] | None]:
        source, target = root / relative, destination / relative
        status = os.stat(source)
        read_only = bool(getattr(status, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_READONLY", 0)) \
            or not status.st_mode & stat.S_IWUSR
        if relative.casefold() in real or read_only:
            shutil.copy2(source, target)
            return "copied", None
        try:
            os.link(source, target)
        except OSError:
            shutil.copy2(source, target)
            return "unlinkable", None
        return "linked", (status.st_size, status.st_mtime_ns)

    placed = map_ordered(place, files)
    outcomes = [outcome for outcome, _ in placed]
    return {
        "mode": "hard_link",
        "linked": outcomes.count("linked"),
        "copied": outcomes.count("copied"),
        "unlinkable": outcomes.count("unlinkable"),
        # What each linked library file looked like when it was linked.
        "guard": {relative: signature for relative, (outcome, signature) in zip(files, placed) if outcome == "linked"},
    }


def verify_untouched(root: Path, staged: dict[str, Any]) -> dict[str, Any]:
    """Fail when a library file that was linked into the staged root has changed since.

    A build only reads the library. With links, a write to a staged file would be a write
    to the library, so this is checked rather than assumed.
    """
    guard = staged.get("guard") or {}
    if not guard:
        return {"mode": staged.get("mode"), "checked": 0, "changed": 0}
    root = root.resolve()

    def current(relative: str) -> tuple[int, int] | None:
        try:
            return _signature(root / relative)
        except OSError:
            return None

    names = list(guard)
    changed = sorted(relative for relative, now in zip(names, map_ordered(current, names)) if now != tuple(guard[relative]))
    if changed:
        raise RuntimeError(f"library changed during the staged build ({len(changed)} files, e.g. {changed[0]}); "
                           "the candidate is not sealed, rebuild it")
    return {"mode": staged.get("mode"), "checked": len(guard), "changed": 0}


def remove_files(path: Path) -> None:
    """Unlink a staged root's files in parallel, best effort; the caller removes what is left."""
    if not path.is_dir():
        return
    _, files = _walk(path, ignored=())

    def unlink(relative: str) -> None:
        try:
            os.unlink(path / relative)
        except OSError:
            pass

    map_ordered(unlink, files)
