# tests/test_extractor.py
import json
import sqlite3
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


@pytest.fixture
def cursor_db(tmp_path):
    """Create a fake Cursor state.vscdb with test conversations."""
    db_path = tmp_path / "state.vscdb"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE ItemTable ([key] TEXT UNIQUE ON CONFLICT REPLACE, value BLOB)")

    chat_data = json.dumps({
        "tabs": [{
            "tabId": "tab-001",
            "chatTitle": "REST API Design",
            "lastSendTime": 1712345678000,
            "bubbles": [
                {"type": "user", "text": "How should I structure the REST API for this project with authentication and rate limiting?"},
                {"type": "ai", "text": "I'd recommend using FastAPI with OAuth2 for authentication. For rate limiting, you can use slowapi which integrates well with FastAPI. Here's the structure I'd suggest for your project."},
                {"type": "user", "text": "What about database migrations? Should I use Alembic or just raw SQL scripts for managing schema changes?"},
                {"type": "ai", "text": "Alembic is the standard choice for SQLAlchemy projects. It handles migration versioning, rollbacks, and auto-generation from model changes. Raw SQL scripts work but you lose the dependency tracking between migrations."},
            ]
        }]
    })

    composer_data = json.dumps({
        "allComposers": [{
            "composerId": "comp-001",
            "name": "Refactor Auth Module",
            "createdAt": 1712345678000,
            "conversation": [
                {"type": 1, "text": "Refactor the authentication module to use JWT tokens instead of session cookies for better scalability"},
                {"type": 2, "text": "I'll refactor the auth module to use JWT. Here are the changes needed across the codebase to support stateless authentication."},
            ]
        }]
    })

    conn.execute("INSERT INTO ItemTable VALUES (?, ?)",
                 ("workbench.panel.aichat.view.aichat.chatdata", chat_data))
    conn.execute("INSERT INTO ItemTable VALUES (?, ?)",
                 ("composerData", composer_data))
    conn.commit()
    conn.close()
    return db_path


def test_parse_cursor_chat(cursor_db):
    from rekall.extractor import parse_cursor_chat
    conversations = parse_cursor_chat(cursor_db)
    assert len(conversations) == 1
    assert conversations[0]["id"] == "cursor_chat_tab-001"
    assert conversations[0]["title"] == "REST API Design"
    assert len(conversations[0]["messages"]) == 4
    assert conversations[0]["messages"][0]["role"] == "user"
    assert conversations[0]["messages"][1]["role"] == "assistant"


def test_parse_cursor_composer(cursor_db):
    from rekall.extractor import parse_cursor_composer
    conversations = parse_cursor_composer(cursor_db)
    assert len(conversations) == 1
    assert conversations[0]["id"] == "cursor_comp_comp-001"
    assert conversations[0]["title"] == "Refactor Auth Module"
    assert len(conversations[0]["messages"]) == 2
    assert conversations[0]["messages"][0]["role"] == "user"
    assert conversations[0]["messages"][1]["role"] == "assistant"


def test_parse_cursor_chat_missing_key(tmp_path):
    """Should return empty list if the key doesn't exist."""
    from rekall.extractor import parse_cursor_chat
    db_path = tmp_path / "empty.vscdb"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE ItemTable ([key] TEXT UNIQUE ON CONFLICT REPLACE, value BLOB)")
    conn.commit()
    conn.close()
    conversations = parse_cursor_chat(db_path)
    assert conversations == []


def test_extract_cursor_sessions_stores_in_db(tmp_path, cursor_db):
    from rekall.extractor import extract_cursor_sessions
    db = Storage(tmp_path / "test.db")
    db.initialize()
    embedder = Embedder()
    processed_log = tmp_path / "processed.log"

    import rekall.extractor as ext
    original = ext.get_cursor_db_path
    ext.get_cursor_db_path = lambda: cursor_db
    try:
        count = extract_cursor_sessions(db, embedder, processed_log)
    finally:
        ext.get_cursor_db_path = original

    assert count >= 1
    docs = db.list_documents(type="session", limit=10)
    cursor_docs = [d for d in docs if "Cursor" in d.title]
    assert len(cursor_docs) >= 1
    assert processed_log.exists()


def test_extract_cursor_skips_processed(tmp_path, cursor_db):
    """Should not re-extract already processed conversations."""
    from rekall.extractor import extract_cursor_sessions
    db = Storage(tmp_path / "test.db")
    db.initialize()
    embedder = Embedder()
    processed_log = tmp_path / "processed.log"

    import rekall.extractor as ext
    original = ext.get_cursor_db_path
    ext.get_cursor_db_path = lambda: cursor_db
    try:
        count1 = extract_cursor_sessions(db, embedder, processed_log)
        count2 = extract_cursor_sessions(db, embedder, processed_log)
    finally:
        ext.get_cursor_db_path = original

    assert count1 >= 1
    assert count2 == 0  # Already processed
