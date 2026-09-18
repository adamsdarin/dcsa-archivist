"""Cross-process publication exclusion, independent of the producer checkout."""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
from typing import Iterator


@contextmanager
def publication_lock(root: Path) -> Iterator[None]:
    library = root.resolve(strict=True)
    if not library.is_dir():
        raise ValueError(f"library root is not a directory: {library}")
    # Outside the corpus: even a first dry run must preserve all corpus bytes.
    # Never unlink this file: replacing its inode could let two writers lock
    # different files for the same library. OS ownership ends on close/crash.
    path = library.parent / f".{library.name}.custodian-publish.lock"
    with path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise RuntimeError(f"publication lock unavailable for {library}; retry after the active publisher exits") from error
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise RuntimeError(f"publication lock unavailable for {library}; retry after the active publisher exits") from error
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
