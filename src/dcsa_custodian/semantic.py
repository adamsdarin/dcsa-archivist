from __future__ import annotations

import contextlib
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


def embed_texts(texts: list[str], batch_size: int = 32, parallel: int | None = None, is_query: bool = False) -> list[bytes]:
    if not texts:
        return []
    if parallel is None:
        parallel = 20 if len(texts) >= 200 else None
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
