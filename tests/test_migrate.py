# tests/test_migrate.py
import json
import pytest
from pathlib import Path
from rekall.migrate import import_instincts, import_vault_notes
from rekall.storage import Storage
from rekall.embedder import Embedder


@pytest.fixture
def db(tmp_path):
    storage = Storage(tmp_path / "test.db")
    storage.initialize()
    return storage


@pytest.fixture
def embedder():
    return Embedder()


@pytest.fixture
def instincts_file(tmp_path):
    path = tmp_path / "instincts.jsonl"
    instincts = [
        {"id": "ins_001", "pattern": "Never use em dashes", "domain": "general",
         "confidence": 0.9, "evidence_count": 5, "last_seen": "2026-04-10",
         "created": "2026-03-01", "source": "user-explicit", "section": "User Preferences"},
        {"id": "ins_002", "pattern": "Always verify factual claims", "domain": "general",
         "confidence": 0.9, "evidence_count": 3, "last_seen": "2026-04-10",
         "created": "2026-03-01", "source": "user-explicit", "section": "Working Standards"},
    ]
    with open(path, "w") as f:
        for inst in instincts:
            f.write(json.dumps(inst) + "\n")
    return path


@pytest.fixture
def vault_dir(tmp_path):
    vault = tmp_path / "vault"
    for folder in ["Research", "Decisions", "Ideas", "Projects", "Sessions"]:
        (vault / folder).mkdir(parents=True)

    (vault / "Research" / "Test Research.md").write_text(
        "---\ndate: 2026-04-01\ntags: [research]\nstatus: active\nsummary: Test\n---\n\n# Test Research\n\nSome research content here that is meaningful."
    )
    (vault / "Decisions" / "Test Decision.md").write_text(
        "---\ndate: 2026-04-01\ntags: [decision]\nstatus: active\nsummary: Test\n---\n\n# Test Decision\n\nWe chose X over Y because of Z."
    )
    return vault


def test_import_instincts(db, instincts_file, embedder):
    count = import_instincts(instincts_file, db, embedder)
    assert count == 2
    mem = db.get_memory("ins_001")
    assert mem is not None
    assert mem.content == "Never use em dashes"
    assert mem.confidence == 0.9
    assert mem.type == "instinct"
    assert mem.source == "user-explicit"


def test_import_instincts_preserves_evidence_count(db, instincts_file, embedder):
    import_instincts(instincts_file, db, embedder)
    mem = db.get_memory("ins_001")
    assert mem.evidence_count == 5


def test_import_vault_notes(db, vault_dir, embedder):
    count = import_vault_notes(vault_dir, db, embedder)
    assert count == 2


def test_import_vault_strips_frontmatter(db, vault_dir, embedder):
    import_vault_notes(vault_dir, db, embedder)
    docs = db.list_documents(limit=10)
    for doc in docs:
        assert "---" not in doc.content[:10]  # frontmatter stripped
