"""End-to-end test: store memories, search, compile MEMORY.md."""
import json
import pytest
from pathlib import Path
from rekall.storage import Storage
from rekall.embedder import Embedder, chunk_text
from rekall.compiler import compile_memory_md
from rekall.schemas import Memory, Document, Chunk


@pytest.fixture
def full_system(tmp_path):
    db = Storage(tmp_path / "test.db")
    db.initialize()
    embedder = Embedder()

    # Add instincts
    instincts = [
        ("mem_001", "Never use em dashes in emails", "general", 0.9, 5),
        ("mem_002", "Always verify factual claims against real-world knowledge", "general", 0.9, 3),
        ("mem_003", "Prefers SQLite for local storage", "dev", 0.7, 2),
    ]
    for id, content, domain, conf, ev in instincts:
        mem = Memory(id=id, content=content, type="instinct", confidence=conf,
                     evidence_count=ev, domain=domain, source="user-explicit")
        db.add_memory(mem)
        vec = embedder.embed(content)
        db.add_memory_vector(id, vec)

    # Add a research document
    research_text = "PostgreSQL handles concurrent writes better than SQLite. " * 20
    doc = Document(id="doc_001", title="Database Comparison Research", content=research_text, type="research")
    chunks_text = chunk_text(research_text, prefix="type: research | topic: Database Comparison Research")
    chunks = [
        Chunk(chunk_id=f"doc_001_chk_{i:03d}", document_id="doc_001", content=c, chunk_index=i)
        for i, c in enumerate(chunks_text)
    ]
    db.add_document(doc, chunks)
    for chunk in chunks:
        vec = embedder.embed(chunk.content)
        db.add_chunk_vector(chunk.chunk_id, vec)

    return db, embedder, tmp_path


def test_recall_finds_instinct_by_meaning(full_system):
    db, embedder, _ = full_system
    query_vec = embedder.embed("formatting rules for email")
    results = db.hybrid_search("formatting rules for email", query_vec, limit=5)
    assert any("em dashes" in r.content for r in results)


def test_recall_finds_document_by_meaning(full_system):
    db, embedder, _ = full_system
    query_vec = embedder.embed("which database handles concurrent writes")
    results = db.hybrid_search("which database handles concurrent writes", query_vec, limit=5)
    assert any("PostgreSQL" in r.content for r in results)


def test_compile_memory_md_from_full_system(full_system):
    db, _, tmp_path = full_system
    output = tmp_path / "MEMORY.md"
    compile_memory_md(db, output)
    content = output.read_text()
    assert "em dashes" in content
    assert "factual claims" in content


def test_full_remember_and_recall_flow(full_system):
    db, embedder, _ = full_system
    # Store a new memory
    new_content = "Nike salary is EUR 3729 per month after taxes"
    new_id = db.next_memory_id()
    mem = Memory(id=new_id, content=new_content, type="fact", confidence=0.9)
    db.add_memory(mem)
    vec = embedder.embed(new_content)
    db.add_memory_vector(new_id, vec)

    # Recall it
    query_vec = embedder.embed("how much do I earn at Nike")
    results = db.hybrid_search("how much do I earn at Nike", query_vec, limit=5)
    assert any("3729" in r.content for r in results)
