"""Compute each deterministic result once per process, and say so when one is reused.

Two kinds of reuse, both counted in ``RunCache.counts``:

- By content, always on. A result that is a pure function of bytes (the era of a DOHA
  decision from its text, ``PRAGMA integrity_check`` of an index file) is kept under the
  SHA-256 of those bytes. The bytes are read and hashed every time the question is
  asked; only the recomputation is skipped. This cannot change an answer.

- By file identity (``trust_unchanged``). A file whose bytes this process has already
  read and hashed is not read again while the operating system reports the same file
  (volume and file ID), the same size and the same modification time, and that time is
  more than a few seconds old. Every byte a command read before is still read by that
  command, once; it is not read a second or third time by a later step of the same
  process. The limit is exactly this: a change that keeps a file's size and restores
  its modification time between two steps of one process is not seen by the second
  step. ``DCSA_REREAD=1`` (or ``release --reread``) turns this off, and every step then
  reads every file again.

Nothing here is persisted. A new process starts with nothing and reads everything.
"""
from __future__ import annotations

import collections
import contextlib
import hashlib
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterator

from .common import sha256_file

RACY_NS = 3_000_000_000


def reread_requested() -> bool:
    """DCSA_REREAD=1: read every file again at every gate, as each command did before."""
    return os.environ.get("DCSA_REREAD", "").strip() not in ("", "0")


class RunCache:
    def __init__(self, trust_unchanged: bool | None = None) -> None:
        if trust_unchanged is None:
            trust_unchanged = not reread_requested()
        self.trust_unchanged = trust_unchanged
        self._files: dict[tuple[int, int], tuple[tuple[int, int], str]] = {}
        self._results: dict[tuple[str, Any], Any] = {}
        self._lock = threading.Lock()
        self._reading: dict[tuple[int, int], threading.Lock] = {}
        self.counts: collections.Counter[str] = collections.Counter()

    # -- file digests -------------------------------------------------------------
    def _identity(self, path: Path) -> tuple[tuple[int, int], tuple[int, int]] | None:
        status = os.stat(path)  # opens the file: accurate for a file with several links
        if not status.st_ino:
            return None
        return (status.st_dev, status.st_ino), (status.st_size, status.st_mtime_ns)

    def lookup(self, path: Path) -> tuple[Any, str | None]:
        """(token, digest): the digest this run already computed for this file, if it may be reused.

        Call before reading; pass the token to ``store`` with the digest of what was read.
        The file is identified before it is read, so a change during the read is never
        recorded as the state the digest describes.
        """
        if not self.trust_unchanged:
            return None, None
        identity = self._identity(path)
        if identity is None:
            return None, None
        held = self._files.get(identity[0])
        if held and held[0] == identity[1]:
            self.counts["files_not_reread"] += 1
            return identity, held[1]
        return identity, None

    def store(self, token: Any, digest: str) -> None:
        self.counts["files_read"] += 1
        # A file modified in the last moments is not remembered: a second write inside the
        # file system's timestamp resolution would leave size and time looking the same.
        if token is not None and time.time_ns() - token[1][1] > RACY_NS:
            with self._lock:
                self._files[token[0]] = (token[1], digest)

    def sha256(self, path: Path, fresh: bool = False) -> str:
        """SHA-256 of the file. ``fresh`` always reads it, and records what was read."""
        token, digest = self.lookup(path)
        if digest is None or fresh:
            if token is None or fresh:
                digest = sha256_file(path)
                self.store(token, digest)
                return digest
            # Two checks asking for the same file at once: the second waits for the first's read.
            with self._lock:
                reading = self._reading.setdefault(token[0], threading.Lock())
            try:
                with reading:
                    held = self._files.get(token[0])
                    if held and held[0] == token[1]:
                        return held[1]
                    digest = sha256_file(path)
                    self.store(token, digest)
            finally:
                with self._lock:
                    self._reading.pop(token[0], None)
        return digest

    def sha256_many(self, paths: list[Path], fresh: bool = False) -> list[str]:
        from .common import map_ordered
        return map_ordered(lambda path: self.sha256(path, fresh), paths)

    # -- results keyed by content ----------------------------------------------------
    def result(self, kind: str, key: Any, compute: Callable[[], Any]) -> Any:
        """``compute()`` once per (kind, key); ``key`` must name every input, by content."""
        slot = (kind, key)
        if slot in self._results:
            self.counts[f"{kind}_reused"] += 1
            return self._results[slot]
        value = compute()
        with self._lock:
            self._results[slot] = value
        self.counts[f"{kind}_computed"] += 1
        return value

    def peek(self, kind: str, key: Any) -> Any:
        return self._results.get((kind, key))

    def holds(self, kind: str) -> bool:
        """True once any result of this kind has been kept."""
        return bool(self.counts[f"{kind}_computed"])

    def put(self, kind: str, key: Any, value: Any) -> None:
        """Replace what is held for (kind, key); None forgets it."""
        with self._lock:
            if value is None:
                self._results.pop((kind, key), None)
            else:
                self._results[(kind, key)] = value

    def summary(self) -> dict[str, Any]:
        return {"trust_unchanged_files": self.trust_unchanged, **dict(sorted(self.counts.items()))}


_default = RunCache()
_active: RunCache | None = None


def current() -> RunCache:
    return _active or _default


@contextlib.contextmanager
def activate(trust_unchanged: bool) -> Iterator[RunCache]:
    """One cache for a whole gated sequence in this process."""
    global _active
    previous, _active = _active, RunCache(trust_unchanged)
    try:
        yield _active
    finally:
        _active = previous


def fingerprint(parts: Any) -> str:
    """SHA-256 over a canonical rendering of nested lists, tuples, strings and numbers."""
    digest = hashlib.sha256()

    def feed(value: Any) -> None:
        if isinstance(value, (list, tuple)):
            digest.update(b"[")
            for item in value:
                feed(item)
            digest.update(b"]")
        elif isinstance(value, dict):
            feed(sorted(value.items()))
        else:
            digest.update(repr(value).encode("utf-8") + b"\x00")

    feed(parts)
    return digest.hexdigest()


_code: str | None = None


def code_fingerprint() -> str:
    """Hash of this package's source and the interpreter and SQLite it runs on.

    A result is only reused by the code that produced it: any edit to the package gives
    a different fingerprint, so nothing computed by other code is accepted.
    """
    global _code
    if _code is None:
        import sqlite3
        import sys
        package = Path(__file__).resolve().parent
        files = sorted(package.glob("*.py"))
        _code = fingerprint([sys.version, sqlite3.sqlite_version,
                             [(path.name, sha256_file(path)) for path in files]])
    return _code
