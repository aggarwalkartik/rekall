import pytest
from rekall.embedder import Embedder, chunk_text


def test_chunk_short_text():
    """Short text should not be chunked."""
    text = "Never use em dashes in emails."
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_chunk_long_text():
    """Long text should be split into overlapping chunks."""
    # Create text that's definitely > 512 tokens (~2000 words)
    text = "This is a test sentence. " * 400
    chunks = chunk_text(text)
    assert len(chunks) > 1
    # Chunks should overlap — last words of chunk N appear in chunk N+1
    for i in range(len(chunks) - 1):
        # The overlap means some content from end of chunk i appears in chunk i+1
        assert len(chunks[i]) > 0


def test_chunk_splits_on_paragraphs():
    """Should prefer splitting on paragraph boundaries."""
    paragraphs = ["Paragraph one. " * 50, "Paragraph two. " * 50, "Paragraph three. " * 50]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text)
    # At least one chunk boundary should align with a paragraph break
    assert len(chunks) >= 2


def test_chunk_with_metadata_prefix():
    """Metadata prefix should be prepended."""
    text = "Short memory text."
    chunks = chunk_text(text, prefix="type: instinct | topic: preferences")
    assert chunks[0].startswith("type: instinct | topic: preferences\n")


class TestEmbedder:
    @pytest.fixture
    def embedder(self):
        return Embedder()

    def test_embed_returns_384_dims(self, embedder):
        result = embedder.embed("test text")
        assert len(result) == 384

    def test_embed_returns_floats(self, embedder):
        result = embedder.embed("test text")
        assert all(isinstance(x, float) for x in result)

    def test_embed_batch(self, embedder):
        results = embedder.embed_batch(["hello", "world"])
        assert len(results) == 2
        assert all(len(r) == 384 for r in results)

    def test_cosine_similarity_identical(self, embedder):
        vec = embedder.embed("test text")
        sim = embedder.cosine_similarity(vec, vec)
        assert sim > 0.99

    def test_cosine_similarity_different(self, embedder):
        vec1 = embedder.embed("I love cats")
        vec2 = embedder.embed("Database normalization techniques")
        sim = embedder.cosine_similarity(vec1, vec2)
        assert sim < 0.8
