from __future__ import annotations

import hashlib
import io
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable


ROBOT_PREFIX = "ROBOT_READABLE_DIRECTORY/"
HUMAN_PREFIX = "HUMAN_READABLE_DIRECTORY/"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def norm(value: object) -> str:
    return str(value or "").replace("\\", "/").lstrip("./")


def normalize_domain(value: object) -> str:
    """Case-fold a domain value.

    The source manifest carries two casings for three domains (TRAINING_AND_AWARENESS vs
    training_and_awareness, and likewise for personnel_vetting and
    information_and_cybersecurity), which silently splits every domain-keyed grouping.
    Enrichment folds them so derived artifacts are consistent, while the raw manifest keeps
    its original values -- the same treatment authority_role gets: derived, not trusted.
    """
    return str(value or "unknown").strip().casefold()


def safe_relative(value: object, prefix: str) -> str:
    path = norm(value)
    if not path.startswith(prefix) or ".." in PurePosixPath(path).parts:
        raise ValueError(f"path must remain under {prefix}: {value}")
    return path


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode_text(data: bytes, errors: str = "replace") -> str:
    """The text ``Path.read_text(encoding="utf-8", errors=errors)`` gives for these bytes.

    Universal newlines included, so a caller that has already read a file's bytes to hash
    them gets the same string every other reader does without opening the file again.
    """
    return io.TextIOWrapper(io.BytesIO(data), encoding="utf-8", errors=errors).read()


def hash_workers() -> int:
    """Threads for file reading and hashing. DCSA_HASH_WORKERS overrides; 1 is serial."""
    setting = os.environ.get("DCSA_HASH_WORKERS", "").strip()
    if setting:
        workers = int(setting)
        if workers < 1:
            raise ValueError("DCSA_HASH_WORKERS must be a positive worker count")
        return workers
    return max(1, min(32, os.cpu_count() or 1))


def map_ordered(function: Callable[[Any], Any], items: Iterable[Any], workers: int | None = None) -> list[Any]:
    """``[function(item) for item in items]`` on a thread pool, results in input order.

    File reads, SHA-256 over more than a few kilobytes and SQLite statements release the
    interpreter lock, so they run on every core. The first failing item, in input order,
    raises the exception a serial loop would raise.
    """
    items = list(items)
    workers = hash_workers() if workers is None else workers
    if workers <= 1 or len(items) < 2:
        return [function(item) for item in items]
    with ThreadPoolExecutor(max_workers=min(workers, len(items))) as pool:
        return list(pool.map(function, items))


def hash_files(paths: Iterable[Path]) -> list[str]:
    """SHA-256 of every file, read in full, in parallel; one digest per path, in order."""
    return map_ordered(sha256_file, paths)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def iter_jsonl(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    with path.open(encoding="utf-8-sig") as handle:
        for number, raw in enumerate(handle, 1):
            if raw.strip():
                yield number, json.loads(raw)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")
    os.replace(temp, path)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    count = 0
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
            count += 1
    os.replace(temp, path)
    return count


def resolve_library_root(project_root: Path, configured: str, override: str | None) -> Path:
    raw = Path(override) if override else Path(configured)
    root = raw if raw.is_absolute() else project_root / raw
    return root.resolve()

