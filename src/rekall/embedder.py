"""Embedding and chunking for Rekall."""
from __future__ import annotations
import math
import sys


def chunk_text(
    text: str,
    max_tokens: int = 512,
    overlap_tokens: int = 64,
    prefix: str | None = None,
) -> list[str]:
    """Split text into chunks. Short text returned as-is.

    Uses character-based approximation: 1 token ~ 4 characters.
    Splits on paragraph > line > sentence boundaries.
    """
    max_chars = max_tokens * 4
    overlap_chars = overlap_tokens * 4

    if prefix:
        text = f"{prefix}\n{text}"

    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0

    while start < len(text):
        end = start + max_chars

        if end >= len(text):
            chunks.append(text[start:])
            break

        # Find best split point: paragraph > line > sentence
        split = text.rfind("\n\n", start, end)
        if split <= start:
            split = text.rfind("\n", start, end)
        if split <= start:
            split = text.rfind(". ", start, end)
            if split > start:
                split += 2  # include the period and space
        if split <= start:
            split = end  # hard cut

        chunks.append(text[start:split])
        start = split - overlap_chars if split - overlap_chars > start else split

    return [c for c in chunks if c.strip()]


class Embedder:
    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        self.model_name = model_name
        self._model = None

    def _load_model(self):
        if self._model is None:
            try:
                from fastembed import TextEmbedding
                self._model = TextEmbedding(model_name=self.model_name)
            except Exception as e:
                print(f"Warning: Could not load embedding model: {e}", file=sys.stderr)
                raise
        return self._model

    def embed(self, text: str) -> list[float]:
        model = self._load_model()
        results = list(model.embed([text]))
        return results[0].tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        model = self._load_model()
        results = list(model.embed(texts))
        return [r.tolist() for r in results]

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
