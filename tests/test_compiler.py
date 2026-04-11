import pytest
import math
from pathlib import Path
from datetime import datetime, timedelta
from rekall.compiler import compile_memory_md
from rekall.storage import Storage
from rekall.schemas import Memory


@pytest.fixture
def db(tmp_path):
    storage = Storage(tmp_path / "test.db")
    storage.initialize()
    return storage


def test_compile_empty_db(db, tmp_path):
    output = tmp_path / "MEMORY.md"
    compile_memory_md(db, output)
    assert output.exists()
    content = output.read_text()
    assert "Rekall" in content or len(content) > 0


def test_compile_includes_active_instincts(db, tmp_path):
    db.add_memory(Memory(
        id="mem_001", content="Never use em dashes", type="instinct",
        confidence=0.9, evidence_count=5,
        last_seen_at=datetime.now().isoformat(),
    ))
    output = tmp_path / "MEMORY.md"
    compile_memory_md(db, output)
    content = output.read_text()
    assert "em dashes" in content


def test_compile_excludes_decayed_instincts(db, tmp_path):
    old_date = (datetime.now() - timedelta(days=365)).isoformat()
    db.add_memory(Memory(
        id="mem_001", content="Old stale preference", type="instinct",
        confidence=0.3, evidence_count=1,
        last_seen_at=old_date, created_at=old_date, updated_at=old_date,
    ))
    output = tmp_path / "MEMORY.md"
    compile_memory_md(db, output)
    content = output.read_text()
    assert "Old stale preference" not in content


def test_compile_groups_by_section(db, tmp_path):
    db.add_memory(Memory(
        id="mem_001", content="Pref A", type="instinct",
        confidence=0.9, evidence_count=3, domain="general",
        last_seen_at=datetime.now().isoformat(),
    ))
    db.add_memory(Memory(
        id="mem_002", content="Pref B", type="instinct",
        confidence=0.9, evidence_count=3, domain="job-search",
        last_seen_at=datetime.now().isoformat(),
    ))
    output = tmp_path / "MEMORY.md"
    compile_memory_md(db, output)
    content = output.read_text()
    assert "general" in content.lower() or "job-search" in content.lower()


def test_compile_shows_confidence_markers(db, tmp_path):
    db.add_memory(Memory(
        id="mem_001", content="High confidence", type="instinct",
        confidence=0.9, evidence_count=5,
        last_seen_at=datetime.now().isoformat(),
    ))
    db.add_memory(Memory(
        id="mem_002", content="Medium confidence", type="instinct",
        confidence=0.5, evidence_count=2,
        last_seen_at=datetime.now().isoformat(),
    ))
    output = tmp_path / "MEMORY.md"
    compile_memory_md(db, output)
    content = output.read_text()
    assert "[M]" in content  # medium marker


def test_compile_detects_contradictions(db, tmp_path):
    db.add_memory(Memory(
        id="mem_001", content="Always use TDD for new features", type="instinct",
        confidence=0.9, evidence_count=3, domain="general",
        last_seen_at=datetime.now().isoformat(),
    ))
    db.add_memory(Memory(
        id="mem_002", content="Never use TDD for new features", type="instinct",
        confidence=0.9, evidence_count=3, domain="general",
        last_seen_at=datetime.now().isoformat(),
    ))
    output = tmp_path / "MEMORY.md"
    compile_memory_md(db, output)
    content = output.read_text()
    assert "conflict" in content.lower()
