# tests/test_sync.py
import json
import pytest
from pathlib import Path
from datetime import datetime
from rekall.sync import sync_to_vault, document_to_markdown, to_title_case
from rekall.storage import Storage
from rekall.schemas import Memory, Document, Chunk


@pytest.fixture
def db(tmp_path):
    storage = Storage(tmp_path / "test.db")
    storage.initialize()
    return storage


@pytest.fixture
def vault(tmp_path):
    vault_path = tmp_path / "vault"
    for folder in ["Research", "Decisions", "Ideas", "Projects"]:
        (vault_path / folder).mkdir(parents=True)
    return vault_path


def test_to_title_case_basic():
    assert to_title_case("my research topic") == "My Research Topic"


def test_to_title_case_preserves_acronyms():
    assert to_title_case("my API research") == "My API Research"
    assert to_title_case("SQL database comparison") == "SQL Database Comparison"
    assert to_title_case("MCP server best practices") == "MCP Server Best Practices"


def test_document_to_markdown_has_frontmatter():
    doc = Document(
        id="doc_001", title="Database Comparison Research",
        content="PostgreSQL handles concurrent writes better than SQLite.",
        type="research", project="Rekall",
    )
    md = document_to_markdown(doc)
    assert "---" in md
    assert "tags: [research]" in md
    assert "status: active" in md
    assert "summary:" in md
    assert "source: rekall-sync" in md


def test_document_to_markdown_has_parent_wikilink():
    doc = Document(
        id="doc_001", title="Test", content="Content here.", type="research",
    )
    md = document_to_markdown(doc)
    assert "Parent: [[Rekall]]" in md


def test_document_to_markdown_preserves_existing_heading():
    doc = Document(
        id="doc_001", title="Test",
        content="# Existing Heading\n\nContent here.",
        type="research",
    )
    md = document_to_markdown(doc)
    # Should not duplicate heading
    assert md.count("# Existing Heading") == 1


def test_sync_creates_research_note(db, vault):
    doc = Document(
        id="doc_001", title="Database Comparison Research",
        content="PostgreSQL handles concurrent writes better than SQLite for multi-user apps.",
        type="research",
    )
    db.add_document(doc, [])
    count = sync_to_vault(db, vault)
    assert count >= 1
    note = vault / "Research" / "Database Comparison Research.md"
    assert note.exists()
    content = note.read_text()
    assert "PostgreSQL" in content
    assert "Parent: [[Rekall]]" in content


def test_sync_creates_decision_note(db, vault):
    doc = Document(
        id="doc_002", title="Hosting Provider Choice",
        content="We chose Cloudflare Pages over Vercel.",
        type="decision",
    )
    db.add_document(doc, [])
    sync_to_vault(db, vault)
    note = vault / "Decisions" / "Hosting Provider Choice.md"
    assert note.exists()


def test_sync_creates_idea_note(db, vault):
    doc = Document(
        id="doc_003", title="Gym Crowd Predictor",
        content="Predict gym crowd levels using historical check-in data.",
        type="idea",
    )
    db.add_document(doc, [])
    sync_to_vault(db, vault)
    note = vault / "Ideas" / "Gym Crowd Predictor.md"
    assert note.exists()


def test_sync_skips_sessions(db, vault):
    doc = Document(
        id="doc_004", title="Session abc123",
        content="Raw conversation text from a session.",
        type="session",
    )
    db.add_document(doc, [])
    count = sync_to_vault(db, vault)
    assert count == 0


def test_sync_skips_already_synced(db, vault):
    from rekall.sync import content_hash
    content = "This was already synced."
    doc = Document(
        id="doc_001", title="Already Synced",
        content=content,
        type="research",
        meta=json.dumps({"synced_to_vault": True, "sync_hash": content_hash(content)}),
    )
    db.add_document(doc, [])
    count = sync_to_vault(db, vault)
    assert count == 0


def test_sync_marks_as_synced(db, vault):
    doc = Document(
        id="doc_001", title="New Research",
        content="Brand new research findings about something interesting.",
        type="research",
    )
    db.add_document(doc, [])
    sync_to_vault(db, vault)

    updated = db.get_document("doc_001")
    assert updated.meta is not None
    meta = json.loads(updated.meta)
    assert meta.get("synced_to_vault") is True
    assert "sync_hash" in meta


def test_sync_updates_changed_document(db, vault):
    doc = Document(
        id="doc_001", title="Evolving Research",
        content="Original content.",
        type="research",
        meta=json.dumps({"synced_to_vault": True, "sync_hash": "old_hash"}),
    )
    db.add_document(doc, [])
    # Manually write a different file to simulate the old sync
    note = vault / "Research" / "Evolving Research.md"
    note.write_text("old content")

    # Update the document content (simulating a remember update)
    db.conn.execute("UPDATE documents SET content = 'Updated new content.' WHERE id = 'doc_001'")
    db.conn.commit()
    # Reset sync hash to trigger re-sync
    db.update_document_meta("doc_001", json.dumps({"synced_to_vault": True, "sync_hash": "old_hash"}))

    count = sync_to_vault(db, vault)
    assert count == 1
    assert "Updated new content" in note.read_text()


def test_sync_uses_title_case_filenames(db, vault):
    doc = Document(
        id="doc_001", title="my API research topic",
        content="Some content about the topic that is interesting.",
        type="research",
    )
    db.add_document(doc, [])
    sync_to_vault(db, vault)
    note = vault / "Research" / "My API Research Topic.md"
    assert note.exists()


def test_sync_creates_instinct_file_in_research(db, vault):
    db.add_memory(Memory(
        id="mem_001", content="Never use em dashes in emails",
        type="instinct", domain="general", confidence=0.9,
        source="user-explicit",
    ))
    db.add_memory(Memory(
        id="mem_002", content="Always verify factual claims",
        type="instinct", domain="general", confidence=0.9,
        source="user-explicit",
    ))
    count = sync_to_vault(db, vault)
    assert count >= 1
    instincts_file = vault / "Research" / "Rekall Instincts.md"
    assert instincts_file.exists()
    content = instincts_file.read_text()
    assert "em dashes" in content
    assert "factual claims" in content
    assert "Parent: [[Rekall]]" in content
