from __future__ import annotations

import contextlib
import hashlib
import os
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np

MODEL_NAME = "BAAI/bge-small-en-v1.5"
VECTOR_DIM = 384
CACHE_DIR = Path(os.environ.get("DCSA_FASTEMBED_CACHE", Path.home() / ".cache" / "dcsa-fastembed"))

# BGE models are trained asymmetrically: passages are embedded as-is, but queries need this
# instruction prefix prepended to land in the same retrieval-relevant region of the embedding
# space. Skipping it costs several points of retrieval accuracy (per the BAAI/bge model card).
# Passage vectors are unaffected -- this only changes how query text is embedded at search time.
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

_model = None


def _get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _model = TextEmbedding(model_name=MODEL_NAME, cache_dir=str(CACHE_DIR))
    return _model


def embedding_workers(count: int, platform: str | None = None) -> int | None:
    """fastembed `parallel` for a batch of `count` texts; None embeds in-process.

    fastembed's multiprocessing pool fails on Windows with WinError 6 ("The handle
    is invalid") in its worker queues and then hangs the build (2026-09-23 and
    2026-09-24 FCL builds), so Windows defaults to in-process embedding. The model,
    batch size and normalization are unchanged, so vectors are the same either way.
    DCSA_EMBED_PARALLEL overrides: 0 or 1 = in-process, N > 1 = N worker processes.
    """
    setting = os.environ.get("DCSA_EMBED_PARALLEL", "").strip()
    if setting:
        workers = int(setting)
        if workers < 0:
            raise ValueError("DCSA_EMBED_PARALLEL must be 0 or a positive worker count")
        return workers if workers > 1 else None
    if (platform or os.name) == "nt":
        return None
    return 20 if count >= 200 else None


def embed_texts(texts: list[str], batch_size: int = 32, parallel: int | None = None, is_query: bool = False) -> list[bytes]:
    if not texts:
        return []
    if parallel is None:
        parallel = embedding_workers(len(texts))
    if is_query:
        texts = [QUERY_INSTRUCTION + text for text in texts]
    model = _get_model()
    vectors = []
    for vector in model.embed(texts, batch_size=batch_size, parallel=parallel):
        vector = np.asarray(vector, dtype="float32")
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        vectors.append(vector.tobytes())
    return vectors


CACHE_TABLE = ("CREATE TABLE IF NOT EXISTS vectors(model TEXT NOT NULL, content_sha256 TEXT NOT NULL, "
               "vector BLOB NOT NULL, PRIMARY KEY(model, content_sha256))")


def embed_texts_cached(texts: list[str], cache_path: Path | None, embed: Any = None,
                       cacheable: bool | None = None) -> tuple[list[bytes], dict[str, Any]]:
    """Passage vectors, reusing ones already computed for identical text.

    A build re-embeds every chunk, though only chunks from new or edited documents
    change. Vectors are keyed by the model name and the SHA-256 of the exact text, so
    a changed chunk or a changed model misses the cache and is embedded afresh; a hit
    returns what this model produced for these bytes before. Passages only: query
    embedding adds an instruction prefix and is never cached here. A cache that cannot
    be read is ignored, never trusted, and everything is embedded.

    Only the real model's vectors are cached: a substituted embedder (a test fake, a
    mock) bypasses the cache entirely, so fake vectors can never be stored under the
    model's name and served to a later real build. ``cacheable`` overrides that, for
    the cache's own tests.
    """
    if cacheable is None:
        cacheable = embed is None or embed is embed_texts
    embed = embed or embed_texts
    if not cacheable:
        cache_path = None
    stats: dict[str, Any] = {"model": MODEL_NAME, "texts": len(texts), "cache": str(cache_path) if cache_path else None}
    if not texts:
        return [], dict(stats, cached=0, embedded=0)
    if cache_path is None:
        return embed(texts), dict(stats, cached=0, embedded=len(texts))
    keys = [hashlib.sha256(text.encode("utf-8")).hexdigest() for text in texts]
    size = VECTOR_DIM * 4
    found: dict[str, bytes] = {}
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.closing(sqlite3.connect(cache_path)) as db:
            db.execute(CACHE_TABLE)
            unique = sorted(set(keys))
            for start in range(0, len(unique), 500):
                batch = unique[start:start + 500]
                rows = db.execute(f"SELECT content_sha256, vector FROM vectors WHERE model=? AND content_sha256 IN "
                                  f"({','.join('?' for _ in batch)})", (MODEL_NAME, *batch))
                found.update((key, vector) for key, vector in rows if len(vector) == size)
    except sqlite3.DatabaseError as exc:
        return embed(texts), dict(stats, cached=0, embedded=len(texts), warning=f"cache unreadable, not used: {exc}")
    missing = {}
    for key, text in zip(keys, texts):
        if key not in found and key not in missing:
            missing[key] = text
    if missing:
        fresh = embed(list(missing.values()))
        if len(fresh) != len(missing) or any(len(vector) != size for vector in fresh):
            raise ValueError("embedding returned the wrong number or size of vectors")
        found.update(zip(missing, fresh))
        try:
            with contextlib.closing(sqlite3.connect(cache_path)) as db, db:
                db.executemany("INSERT OR REPLACE INTO vectors VALUES(?,?,?)",
                               [(MODEL_NAME, key, found[key]) for key in missing])
        except sqlite3.DatabaseError as exc:
            stats["warning"] = f"cache not updated: {exc}"
    return [found[key] for key in keys], dict(stats, cached=len(texts) - sum(1 for k in keys if k in missing),
                                              embedded=len(missing))


def embed_query(query: str) -> bytes:
    return embed_texts([query], is_query=True)[0]


def semantic_search(db_path: Path, query: str, top_k: int = 10) -> list[dict[str, Any]]:
    query_vector = np.frombuffer(embed_query(query), dtype="float32")
    with contextlib.closing(sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT v.chunk_id, v.vector, c.document_id, c.authority_role, c.authority_priority,
                   c.collection_id, c.locator, c.content
            FROM vectors v JOIN corpus c ON c.chunk_id = v.chunk_id
        """).fetchall()
    if not rows:
        return []
    matrix = np.stack([np.frombuffer(row["vector"], dtype="float32") for row in rows])
    scores = matrix @ query_vector
    order = np.argsort(-scores)[:top_k]
    return [
        {
            "chunk_id": rows[i]["chunk_id"],
            "document_id": rows[i]["document_id"],
            "authority_role": rows[i]["authority_role"],
            "authority_priority": rows[i]["authority_priority"],
            "collection_id": rows[i]["collection_id"],
            "locator": rows[i]["locator"],
            "similarity": float(scores[i]),
            "content": rows[i]["content"],
        }
        for i in order
    ]
