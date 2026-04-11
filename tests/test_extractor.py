# tests/test_extractor.py
import json
import pytest
from pathlib import Path
from rekall.extractor import parse_session, filter_messages, extract_sessions
from rekall.storage import Storage
from rekall.embedder import Embedder


def make_event(type: str, text: str, timestamp: str = "2026-04-10T10:00:00") -> dict:
    if type == "user":
        return {"type": "user", "message": {"content": [{"type": "text", "text": text}]}, "timestamp": timestamp}
    elif type == "assistant":
        return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}, "timestamp": timestamp}
    else:
        return {"type": type, "timestamp": timestamp}


@pytest.fixture
def session_file(tmp_path):
    events = [
        make_event("user", "Let's build a REST API for the project"),
        make_event("assistant", "I'll help you build a REST API. Let me start by setting up the project structure with FastAPI."),
        make_event("user", "I decided to use PostgreSQL instead of SQLite for this because we need concurrent writes"),
        make_event("assistant", "Good decision. PostgreSQL handles concurrent writes much better than SQLite for multi-user applications. Let me update the database configuration."),
        make_event("user", "ok"),  # Short message — should be filtered
        make_event("system", "Progress update"),  # System message — should be filtered
    ]
    path = tmp_path / "projects" / "test-project" / "session123.jsonl"
    path.parent.mkdir(parents=True)
    with open(path, "w") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")
    return path


def test_parse_session(session_file):
    messages = parse_session(session_file)
    assert len(messages) >= 2
    assert all("text" in m for m in messages)
    assert all("role" in m for m in messages)


def test_filter_messages_removes_short():
    messages = [
        {"role": "user", "text": "ok"},
        {"role": "user", "text": "Let's build a REST API for the task management project"},
        {"role": "assistant", "text": "yes"},
    ]
    filtered = filter_messages(messages)
    assert len(filtered) == 1
    assert "REST API" in filtered[0]["text"]


def test_filter_messages_removes_system():
    messages = [
        {"role": "system", "text": "Progress update"},
        {"role": "user", "text": "Let's discuss the architecture of this new feature in detail"},
    ]
    filtered = filter_messages(messages)
    assert len(filtered) == 1


def test_extract_sessions_stores_in_db(tmp_path, session_file):
    db = Storage(tmp_path / "test.db")
    db.initialize()
    embedder = Embedder()
    processed_log = tmp_path / "sessions-processed.log"

    extract_sessions(
        session_dirs=[session_file.parent.parent],
        db=db,
        embedder=embedder,
        processed_log=processed_log,
    )

    # Should have stored something
    docs = db.list_documents(type="session", limit=10)
    assert len(docs) >= 1

    # Should have marked as processed
    assert processed_log.exists()
    assert "session123" in processed_log.read_text()
