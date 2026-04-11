import pytest
from pathlib import Path
from rekall.storage import Storage
from rekall.schemas import Memory, Document, Chunk


@pytest.fixture
def db(tmp_path):
    storage = Storage(tmp_path / "test.db")
    storage.initialize()
    return storage


def test_initialize_creates_tables(db):
    tables = db.list_tables()
    assert "memories" in tables
    assert "documents" in tables
    assert "chunks" in tables
    assert "rekall_meta" in tables


def test_initialize_sets_pragmas(db):
    journal_mode = db.execute_scalar("PRAGMA journal_mode")
    assert journal_mode == "wal"


def test_initialize_sets_schema_version(db):
    version = db.get_schema_version()
    assert version == 1


def test_add_memory(db):
    mem = Memory(id="mem_001", content="Never use em dashes", type="instinct")
    db.add_memory(mem)
    result = db.get_memory("mem_001")
    assert result is not None
    assert result.content == "Never use em dashes"
    assert result.type == "instinct"


def test_add_memory_duplicate_id_raises(db):
    mem = Memory(id="mem_001", content="First", type="fact")
    db.add_memory(mem)
    with pytest.raises(Exception):
        db.add_memory(mem)


def test_update_memory_evidence(db):
    mem = Memory(id="mem_001", content="Test", type="fact", evidence_count=1)
    db.add_memory(mem)
    db.bump_evidence("mem_001")
    result = db.get_memory("mem_001")
    assert result.evidence_count == 2


def test_soft_delete_memory(db):
    mem = Memory(id="mem_001", content="Test", type="fact")
    db.add_memory(mem)
    db.soft_delete_memory("mem_001")
    result = db.get_memory("mem_001")
    assert result.status == "deleted"
    assert result.deleted_at is not None


def test_list_memories_excludes_deleted(db):
    db.add_memory(Memory(id="mem_001", content="Active", type="fact"))
    db.add_memory(Memory(id="mem_002", content="Deleted", type="fact"))
    db.soft_delete_memory("mem_002")
    results = db.list_memories()
    assert len(results) == 1
    assert results[0].id == "mem_001"


def test_list_memories_filter_by_type(db):
    db.add_memory(Memory(id="mem_001", content="Pref", type="instinct"))
    db.add_memory(Memory(id="mem_002", content="Fact", type="fact"))
    results = db.list_memories(type="instinct")
    assert len(results) == 1
    assert results[0].type == "instinct"


def test_add_document_and_chunks(db):
    doc = Document(id="doc_001", title="Test Doc", content="Full content here", type="research")
    chunks = [
        Chunk(chunk_id="chk_001", document_id="doc_001", content="Full content here", chunk_index=0),
    ]
    db.add_document(doc, chunks)
    result = db.get_document("doc_001")
    assert result is not None
    assert result.title == "Test Doc"
    doc_chunks = db.get_chunks("doc_001")
    assert len(doc_chunks) == 1


def test_fts_search_memories(db):
    db.add_memory(Memory(id="mem_001", content="Always use SQLite for local storage", type="fact"))
    db.add_memory(Memory(id="mem_002", content="Never use em dashes in emails", type="instinct"))
    results = db.fts_search_memories("SQLite")
    assert len(results) >= 1
    assert any(r.id == "mem_001" for r in results)


def test_fts_search_chunks(db):
    doc = Document(id="doc_001", title="DB Guide", content="Long content", type="research")
    chunks = [
        Chunk(chunk_id="chk_001", document_id="doc_001", content="SQLite is great for embedded databases", chunk_index=0),
        Chunk(chunk_id="chk_002", document_id="doc_001", content="PostgreSQL is better for servers", chunk_index=1),
    ]
    db.add_document(doc, chunks)
    results = db.fts_search_chunks("SQLite")
    assert len(results) >= 1
    assert any(r.chunk_id == "chk_001" for r in results)


def test_next_memory_id(db):
    assert db.next_memory_id() == "mem_001"
    db.add_memory(Memory(id="mem_001", content="First", type="fact"))
    assert db.next_memory_id() == "mem_002"


def test_next_document_id(db):
    assert db.next_document_id() == "doc_001"
