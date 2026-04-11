# tests/test_search.py
import pytest
from rekall.storage import Storage
from rekall.embedder import Embedder
from rekall.schemas import Memory, Document, Chunk, RecallResult


@pytest.fixture
def embedder():
    return Embedder()


@pytest.fixture
def db(tmp_path, embedder):
    storage = Storage(tmp_path / "test.db")
    storage.initialize()

    # Add test memories with embeddings
    memories = [
        Memory(id="mem_001", content="Always use SQLite for local data storage", type="instinct", confidence=0.9, evidence_count=3),
        Memory(id="mem_002", content="Never use em dashes in emails", type="instinct", confidence=0.9, evidence_count=5),
        Memory(id="mem_003", content="Chose Cloudflare Pages over Vercel for hosting", type="decision", confidence=0.8),
        Memory(id="mem_004", content="Nike net salary is EUR 3729 per month", type="fact", confidence=0.9),
    ]
    for mem in memories:
        storage.add_memory(mem)
        vec = embedder.embed(mem.content)
        storage.add_memory_vector(mem.id, vec)

    # Add a document with chunks
    doc = Document(id="doc_001", title="Hosting Comparison", content="Long research about hosting options...", type="research")
    chunks = [
        Chunk(chunk_id="chk_001", document_id="doc_001", content="Cloudflare Pages offers free hosting with edge deployment and fast builds", chunk_index=0),
        Chunk(chunk_id="chk_002", document_id="doc_001", content="Vercel has better Next.js integration but charges for bandwidth", chunk_index=1),
    ]
    storage.add_document(doc, chunks)
    for chunk in chunks:
        vec = embedder.embed(chunk.content)
        storage.add_chunk_vector(chunk.chunk_id, vec)

    return storage


def test_hybrid_search_finds_by_keyword(db, embedder):
    """BM25 should catch exact terms."""
    query_vec = embedder.embed("em dashes")
    results = db.hybrid_search("em dashes", query_vec, limit=5)
    assert any(r.id == "mem_002" for r in results)


def test_hybrid_search_finds_by_meaning(db, embedder):
    """Vector search should catch semantic intent."""
    query_vec = embedder.embed("where should I host my website?")
    results = db.hybrid_search("where should I host my website?", query_vec, limit=5)
    assert any(r.id == "mem_003" or r.source_document == "doc_001" for r in results)


def test_hybrid_search_returns_recall_results(db, embedder):
    query_vec = embedder.embed("salary")
    results = db.hybrid_search("salary", query_vec, limit=5)
    assert all(isinstance(r, RecallResult) for r in results)
    assert all(hasattr(r, 'score') for r in results)


def test_hybrid_search_respects_limit(db, embedder):
    query_vec = embedder.embed("hosting")
    results = db.hybrid_search("hosting", query_vec, limit=2)
    assert len(results) <= 2


def test_hybrid_search_chunk_includes_document_pointer(db, embedder):
    query_vec = embedder.embed("Cloudflare edge deployment")
    results = db.hybrid_search("Cloudflare edge deployment", query_vec, limit=5)
    chunk_results = [r for r in results if r.source_document is not None]
    if chunk_results:
        assert chunk_results[0].source_document == "doc_001"
        assert chunk_results[0].source_title == "Hosting Comparison"
