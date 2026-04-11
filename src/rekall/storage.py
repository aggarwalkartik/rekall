"""SQLite storage layer with FTS5 and sqlite-vec support."""
from __future__ import annotations
import sqlite3
import sqlite_vec
from datetime import datetime
from pathlib import Path
from rekall.schemas import Memory, Document, Chunk, RecallResult

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS rekall_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS memories (
    id              TEXT PRIMARY KEY,
    content         TEXT NOT NULL,
    type            TEXT NOT NULL,
    source          TEXT,
    confidence      REAL DEFAULT 1.0,
    evidence_count  INTEGER DEFAULT 1,
    domain          TEXT,
    project         TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL,
    status          TEXT DEFAULT 'active',
    deleted_at      TEXT,
    meta            TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    content         TEXT NOT NULL,
    type            TEXT NOT NULL,
    source_path     TEXT,
    project         TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    status          TEXT DEFAULT 'active',
    deleted_at      TEXT,
    meta            TEXT
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id        TEXT PRIMARY KEY,
    document_id     TEXT REFERENCES documents(id),
    content         TEXT NOT NULL,
    chunk_index     INTEGER
);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content,
    content='memories',
    content_rowid='rowid'
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    content,
    content='chunks',
    content_rowid='rowid'
);

-- FTS sync triggers for memories
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content) VALUES (new.rowid, new.content);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content) VALUES ('delete', old.rowid, old.content);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content) VALUES ('delete', old.rowid, old.content);
    INSERT INTO memories_fts(rowid, content) VALUES (new.rowid, new.content);
END;

-- FTS sync triggers for chunks
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, content) VALUES (new.rowid, new.content);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES ('delete', old.rowid, old.content);
END;

CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES ('delete', old.rowid, old.content);
    INSERT INTO chunks_fts(rowid, content) VALUES (new.rowid, new.content);
END;
"""

VEC_SCHEMA_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS vec_memories USING vec0(
    id TEXT PRIMARY KEY,
    embedding float[384]
);

CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(
    chunk_id TEXT PRIMARY KEY,
    embedding float[384]
);
"""


class Storage:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn: sqlite3.Connection | None = None

    def initialize(self) -> None:
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA busy_timeout = 5000")
        self.conn.execute("PRAGMA wal_autocheckpoint = 1000")
        self.conn.executescript(SCHEMA_SQL)
        # Load sqlite-vec extension and create vector tables
        self.conn.enable_load_extension(True)
        sqlite_vec.load(self.conn)
        self.conn.enable_load_extension(False)
        self.conn.executescript(VEC_SCHEMA_SQL)
        # Set schema version if not set
        self.conn.execute(
            "INSERT OR IGNORE INTO rekall_meta (key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        self.conn.commit()

    def close(self) -> None:
        if self.conn:
            self.conn.close()

    def execute_scalar(self, sql: str) -> str | None:
        row = self.conn.execute(sql).fetchone()
        return row[0] if row else None

    def get_schema_version(self) -> int:
        val = self.execute_scalar("SELECT value FROM rekall_meta WHERE key = 'schema_version'")
        return int(val) if val else 0

    def list_tables(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        return [r[0] for r in rows]

    # --- Memory CRUD ---

    def add_memory(self, mem: Memory) -> None:
        self.conn.execute(
            """INSERT INTO memories (id, content, type, source, confidence, evidence_count,
               domain, project, created_at, updated_at, last_seen_at, status, deleted_at, meta)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (mem.id, mem.content, mem.type, mem.source, mem.confidence, mem.evidence_count,
             mem.domain, mem.project, mem.created_at, mem.updated_at, mem.last_seen_at,
             mem.status, mem.deleted_at, mem.meta),
        )
        self.conn.commit()

    def get_memory(self, memory_id: str) -> Memory | None:
        row = self.conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        if not row:
            return None
        return Memory(**dict(row))

    def bump_evidence(self, memory_id: str) -> None:
        now = datetime.now().isoformat()
        self.conn.execute(
            "UPDATE memories SET evidence_count = evidence_count + 1, last_seen_at = ?, updated_at = ? WHERE id = ?",
            (now, now, memory_id),
        )
        self.conn.commit()

    def soft_delete_memory(self, memory_id: str) -> None:
        now = datetime.now().isoformat()
        self.conn.execute(
            "UPDATE memories SET status = 'deleted', deleted_at = ?, updated_at = ? WHERE id = ?",
            (now, now, memory_id),
        )
        self.conn.commit()

    def list_memories(
        self, type: str | None = None, project: str | None = None,
        status: str = "active", limit: int = 20,
    ) -> list[Memory]:
        sql = "SELECT * FROM memories WHERE status = ?"
        params: list = [status]
        if type:
            sql += " AND type = ?"
            params.append(type)
        if project:
            sql += " AND project = ?"
            params.append(project)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [Memory(**dict(r)) for r in rows]

    def next_memory_id(self) -> str:
        row = self.conn.execute(
            "SELECT id FROM memories ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        if not row:
            return "mem_001"
        num = int(row[0].split("_")[1]) + 1
        return f"mem_{num:03d}"

    # --- Document CRUD ---

    def add_document(self, doc: Document, chunks: list[Chunk]) -> None:
        self.conn.execute(
            """INSERT INTO documents (id, title, content, type, source_path, project,
               created_at, updated_at, status, deleted_at, meta)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (doc.id, doc.title, doc.content, doc.type, doc.source_path, doc.project,
             doc.created_at, doc.updated_at, doc.status, doc.deleted_at, doc.meta),
        )
        for chunk in chunks:
            self.conn.execute(
                "INSERT INTO chunks (chunk_id, document_id, content, chunk_index) VALUES (?, ?, ?, ?)",
                (chunk.chunk_id, chunk.document_id, chunk.content, chunk.chunk_index),
            )
        self.conn.commit()

    def get_document(self, doc_id: str) -> Document | None:
        row = self.conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not row:
            return None
        return Document(**dict(row))

    def get_chunks(self, doc_id: str) -> list[Chunk]:
        rows = self.conn.execute(
            "SELECT * FROM chunks WHERE document_id = ? ORDER BY chunk_index", (doc_id,)
        ).fetchall()
        return [Chunk(**dict(r)) for r in rows]

    def next_document_id(self) -> str:
        row = self.conn.execute(
            "SELECT id FROM documents ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        if not row:
            return "doc_001"
        num = int(row[0].split("_")[1]) + 1
        return f"doc_{num:03d}"

    # --- FTS Search ---

    def fts_search_memories(self, query: str, limit: int = 20) -> list[Memory]:
        rows = self.conn.execute(
            """SELECT m.* FROM memories_fts fts
               JOIN memories m ON m.rowid = fts.rowid
               WHERE memories_fts MATCH ? AND m.status = 'active'
               ORDER BY rank LIMIT ?""",
            (query, limit),
        ).fetchall()
        return [Memory(**dict(r)) for r in rows]

    def fts_search_chunks(self, query: str, limit: int = 20) -> list[Chunk]:
        rows = self.conn.execute(
            """SELECT c.* FROM chunks_fts fts
               JOIN chunks c ON c.rowid = fts.rowid
               WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?""",
            (query, limit),
        ).fetchall()
        return [Chunk(**dict(r)) for r in rows]

    # --- Vector operations (added in Task 3) ---

    def add_memory_vector(self, memory_id: str, embedding: list[float]) -> None:
        self.conn.execute(
            "INSERT INTO vec_memories (id, embedding) VALUES (?, ?)",
            (memory_id, sqlite_vec.serialize_float32(embedding)),
        )
        self.conn.commit()

    def add_chunk_vector(self, chunk_id: str, embedding: list[float]) -> None:
        self.conn.execute(
            "INSERT INTO vec_chunks (chunk_id, embedding) VALUES (?, ?)",
            (chunk_id, sqlite_vec.serialize_float32(embedding)),
        )
        self.conn.commit()

    def remove_memory_vector(self, memory_id: str) -> None:
        self.conn.execute("DELETE FROM vec_memories WHERE id = ?", (memory_id,))
        self.conn.commit()

    def vec_search_memories(self, embedding: list[float], limit: int = 20) -> list[tuple[str, float]]:
        rows = self.conn.execute(
            """SELECT id, distance FROM vec_memories
               WHERE embedding MATCH ? ORDER BY distance LIMIT ?""",
            (sqlite_vec.serialize_float32(embedding), limit),
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def vec_search_chunks(self, embedding: list[float], limit: int = 20) -> list[tuple[str, float]]:
        rows = self.conn.execute(
            """SELECT chunk_id, distance FROM vec_chunks
               WHERE embedding MATCH ? ORDER BY distance LIMIT ?""",
            (sqlite_vec.serialize_float32(embedding), limit),
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def memory_content_hash_exists(self, content_hash: str) -> str | None:
        """Check if a memory with this content hash exists. Returns memory ID or None."""
        row = self.conn.execute(
            "SELECT id FROM memories WHERE status = 'active' AND meta LIKE ?",
            (f'%"content_hash": "{content_hash}"%',),
        ).fetchone()
        return row[0] if row else None
