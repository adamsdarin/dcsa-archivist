"""The embedding cache reuses vectors only for identical text under the same model."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from dcsa_custodian import semantic
from dcsa_custodian.semantic import VECTOR_DIM, embed_texts_cached


def cached(texts, cache, embed):
    return embed_texts_cached(texts, cache, embed, cacheable=True)


class CountingEmbedder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, texts: list[str]) -> list[bytes]:
        self.calls.append(list(texts))
        return [(text.encode("utf-8") * VECTOR_DIM * 4)[:VECTOR_DIM * 4].ljust(VECTOR_DIM * 4, b"\0") for text in texts]


class EmbeddingCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.cache = Path(temp.name) / "embedding_cache.sqlite"

    def test_only_new_text_is_embedded_on_the_next_build(self) -> None:
        embed = CountingEmbedder()
        first, stats = cached(["alpha", "beta"], self.cache, embed)
        self.assertEqual((stats["cached"], stats["embedded"]), (0, 2))
        second, stats = cached(["beta", "gamma", "alpha"], self.cache, embed)
        self.assertEqual(embed.calls[-1], ["gamma"])
        self.assertEqual((stats["cached"], stats["embedded"]), (2, 1))
        self.assertEqual(second[0], first[1])
        self.assertEqual(second[2], first[0])

    def test_repeated_text_in_one_build_is_embedded_once(self) -> None:
        embed = CountingEmbedder()
        vectors, stats = cached(["same", "same", "other"], self.cache, embed)
        self.assertEqual(embed.calls, [["same", "other"]])
        self.assertEqual(vectors[0], vectors[1])
        self.assertEqual(stats["embedded"], 2)

    def test_a_different_model_does_not_reuse_vectors(self) -> None:
        embed = CountingEmbedder()
        cached(["alpha"], self.cache, embed)
        with mock.patch.object(semantic, "MODEL_NAME", "some/other-model"):
            _, stats = cached(["alpha"], self.cache, embed)
        self.assertEqual(stats["embedded"], 1)

    def test_a_wrong_sized_cached_vector_is_ignored(self) -> None:
        embed = CountingEmbedder()
        cached(["alpha"], self.cache, embed)
        with closing(sqlite3.connect(self.cache)) as db, db:
            db.execute("UPDATE vectors SET vector=?", (b"short",))
        vectors, stats = cached(["alpha"], self.cache, embed)
        self.assertEqual(stats["embedded"], 1)
        self.assertEqual(len(vectors[0]), VECTOR_DIM * 4)

    def test_an_unreadable_cache_is_not_trusted(self) -> None:
        self.cache.write_bytes(b"this is not a database")
        embed = CountingEmbedder()
        vectors, stats = cached(["alpha", "beta"], self.cache, embed)
        self.assertEqual(stats["embedded"], 2)
        self.assertIn("not used", stats["warning"])
        self.assertEqual(len(vectors), 2)

    def test_no_cache_path_embeds_everything(self) -> None:
        embed = CountingEmbedder()
        _, stats = cached(["alpha", "beta"], None, embed)
        self.assertEqual((stats["cached"], stats["embedded"]), (0, 2))

    def test_a_substituted_embedder_never_touches_the_cache(self) -> None:
        embed = CountingEmbedder()
        _, stats = embed_texts_cached(["alpha"], self.cache, embed)
        self.assertIsNone(stats["cache"])
        self.assertFalse(self.cache.exists(), "fake vectors must not be stored under the real model's name")


if __name__ == "__main__":
    unittest.main()
