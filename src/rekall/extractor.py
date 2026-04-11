"""Session extraction pipeline — parse Claude Code JSONL sessions into memories."""
from __future__ import annotations
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

from rekall.embedder import Embedder, chunk_text
from rekall.schemas import Chunk, Document
from rekall.storage import Storage

MIN_MESSAGE_WORDS = 8


def parse_session(jsonl_path: Path) -> list[dict]:
    """Parse a JSONL session file into message dicts."""
    messages = []
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type")
            if event_type not in ("user", "assistant"):
                continue

            # Extract text from message content blocks
            content_blocks = event.get("message", {}).get("content", [])
            texts = []
            for block in content_blocks:
                if block.get("type") == "text":
                    texts.append(block["text"])
                # Skip tool_use and tool_result blocks
            if texts:
                messages.append({
                    "role": event_type,
                    "text": "\n".join(texts),
                    "timestamp": event.get("timestamp", ""),
                })
    return messages


def filter_messages(messages: list[dict]) -> list[dict]:
    """Remove noise: short messages, system messages, boilerplate."""
    filtered = []
    for msg in messages:
        if msg["role"] not in ("user", "assistant"):
            continue
        word_count = len(msg["text"].split())
        if word_count < MIN_MESSAGE_WORDS:
            continue
        filtered.append(msg)
    return filtered


def extract_sessions(
    session_dirs: list[Path],
    db: Storage,
    embedder: Embedder | None,
    processed_log: Path,
) -> int:
    """Extract unprocessed sessions into the database. Returns count of sessions processed."""
    # Read already-processed session IDs
    processed_ids: set[str] = set()
    if processed_log.exists():
        processed_ids = set(processed_log.read_text().strip().split("\n"))

    count = 0
    for session_dir in session_dirs:
        if not session_dir.exists():
            continue
        for jsonl_file in sorted(session_dir.glob("**/*.jsonl")):
            # Skip subagent files
            if "subagent" in str(jsonl_file):
                continue

            session_id = jsonl_file.stem
            if session_id in processed_ids:
                continue

            messages = parse_session(jsonl_file)
            if len(messages) < 5:
                # Skip short sessions, but mark as processed
                processed_ids.add(session_id)
                continue

            filtered = filter_messages(messages)
            if not filtered:
                processed_ids.add(session_id)
                continue

            # Combine filtered messages into session text
            session_text = "\n\n".join(
                f"[{m['role']}]: {m['text']}" for m in filtered
            )

            # Chunk and store
            doc_id = db.next_document_id()
            doc = Document(
                id=doc_id,
                title=f"Session {session_id[:20]}",
                content=session_text,
                type="session",
                source_path=str(jsonl_file),
            )
            text_chunks = chunk_text(session_text, prefix=f"type: session | id: {session_id}")
            chunks = [
                Chunk(
                    chunk_id=f"{doc_id}_chk_{i:03d}",
                    document_id=doc_id,
                    content=c,
                    chunk_index=i,
                )
                for i, c in enumerate(text_chunks)
            ]
            db.add_document(doc, chunks)

            if embedder:
                try:
                    vecs = embedder.embed_batch([c.content for c in chunks])
                    for chunk, vec in zip(chunks, vecs):
                        db.add_chunk_vector(chunk.chunk_id, vec)
                except Exception as e:
                    print(f"Warning: Failed to embed session {session_id}: {e}", file=sys.stderr)

            processed_ids.add(session_id)
            count += 1

    # Write processed log
    processed_log.parent.mkdir(parents=True, exist_ok=True)
    processed_log.write_text("\n".join(sorted(processed_ids)))

    return count


def get_cursor_db_path() -> Path | None:
    """Find Cursor's state.vscdb across platforms."""
    system = platform.system()
    if system == "Darwin":
        p = Path.home() / "Library/Application Support/Cursor/User/globalStorage/state.vscdb"
    elif system == "Linux":
        p = Path.home() / ".config/Cursor/User/globalStorage/state.vscdb"
    elif system == "Windows":
        p = Path(os.environ.get("APPDATA", "")) / "Cursor/User/globalStorage/state.vscdb"
    else:
        return None
    return p if p.exists() else None


def parse_cursor_chat(db_path: Path) -> list[dict]:
    """Parse sidebar chat conversations from Cursor's state.vscdb."""
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT value FROM ItemTable WHERE key = ?",
            ("workbench.panel.aichat.view.aichat.chatdata",)
        ).fetchone()
        if not row:
            return []
        data = json.loads(row[0])
        conversations = []
        for tab in data.get("tabs", []):
            tab_id = tab.get("tabId", "unknown")
            messages = []
            for bubble in tab.get("bubbles", []):
                role = "user" if bubble.get("type") == "user" else "assistant"
                text = bubble.get("text", "")
                if text:
                    messages.append({"role": role, "text": text})
            if messages:
                conversations.append({
                    "id": f"cursor_chat_{tab_id}",
                    "title": tab.get("chatTitle", "Untitled"),
                    "messages": messages,
                    "timestamp": tab.get("lastSendTime"),
                })
        return conversations
    finally:
        conn.close()


def parse_cursor_composer(db_path: Path) -> list[dict]:
    """Parse composer/agent conversations from Cursor's state.vscdb."""
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT value FROM ItemTable WHERE key = ?",
            ("composerData",)
        ).fetchone()
        if not row:
            return []
        data = json.loads(row[0])
        conversations = []
        for composer in data.get("allComposers", []):
            comp_id = composer.get("composerId", "unknown")
            messages = []
            for msg in composer.get("conversation", []):
                role = "user" if msg.get("type") == 1 else "assistant"
                text = msg.get("text", "")
                if text:
                    messages.append({"role": role, "text": text})
            if messages:
                conversations.append({
                    "id": f"cursor_comp_{comp_id}",
                    "title": composer.get("name", "Untitled"),
                    "messages": messages,
                    "timestamp": composer.get("createdAt"),
                })
        return conversations
    finally:
        conn.close()


def extract_cursor_sessions(
    db: Storage,
    embedder: Embedder | None,
    processed_log: Path,
) -> int:
    """Extract unprocessed Cursor conversations into Rekall. Returns count."""
    cursor_db = get_cursor_db_path()
    if not cursor_db:
        return 0

    # Read already-processed IDs
    processed_ids: set[str] = set()
    if processed_log.exists():
        processed_ids = set(processed_log.read_text().strip().split("\n"))

    conversations = []
    try:
        conversations.extend(parse_cursor_chat(cursor_db))
    except Exception as e:
        print(f"Warning: Failed to parse Cursor chat: {e}", file=sys.stderr)
    try:
        conversations.extend(parse_cursor_composer(cursor_db))
    except Exception as e:
        print(f"Warning: Failed to parse Cursor composer: {e}", file=sys.stderr)

    count = 0
    for conv in conversations:
        if conv["id"] in processed_ids:
            continue

        filtered = filter_messages(conv["messages"])
        if len(filtered) < 3:
            processed_ids.add(conv["id"])
            continue

        session_text = "\n\n".join(
            f"[{m['role']}]: {m['text']}" for m in filtered
        )

        doc_id = db.next_document_id()
        doc = Document(
            id=doc_id,
            title=f"Cursor: {conv['title'][:60]}",
            content=session_text,
            type="session",
            source_path=str(cursor_db),
            meta=json.dumps({"source": "cursor", "cursor_id": conv["id"]}),
        )
        text_chunks = chunk_text(session_text, prefix=f"type: session | source: cursor | title: {conv['title'][:40]}")
        chunks = [
            Chunk(
                chunk_id=f"{doc_id}_chk_{i:03d}",
                document_id=doc_id,
                content=c,
                chunk_index=i,
            )
            for i, c in enumerate(text_chunks)
        ]
        db.add_document(doc, chunks)

        if embedder:
            try:
                vecs = embedder.embed_batch([c.content for c in chunks])
                for chunk, vec in zip(chunks, vecs):
                    db.add_chunk_vector(chunk.chunk_id, vec)
            except Exception as e:
                print(f"Warning: Failed to embed Cursor conversation {conv['id']}: {e}", file=sys.stderr)

        processed_ids.add(conv["id"])
        count += 1

    # Write processed log
    processed_log.parent.mkdir(parents=True, exist_ok=True)
    processed_log.write_text("\n".join(sorted(processed_ids)))

    return count


def main():
    """Entry point for rekall-extract. Use --background to run in background."""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--cursor", action="store_true", help="Extract Cursor conversations")
    args = parser.parse_args()

    if args.background:
        # Fork to background
        if os.name == "nt":
            # Windows: use subprocess
            log_dir = Path.home() / ".rekall"
            log_dir.mkdir(parents=True, exist_ok=True)
            subprocess.Popen(
                [sys.executable, "-m", "rekall.extractor"],
                creationflags=subprocess.DETACHED_PROCESS,
                stdout=subprocess.DEVNULL,
                stderr=open(log_dir / "extract.log", "a"),
            )
            return  # Parent exits, child runs independently
        else:
            # Unix: fork
            pid = os.fork()
            if pid > 0:
                # Parent returns immediately
                return
            # Child continues
            os.setsid()

    from rekall.config import get_config
    config = get_config()
    db = Storage(config.db_path)
    db.initialize()

    try:
        embedder = Embedder(config.model_name)
    except Exception:
        embedder = None

    processed_log = config.data_dir / "sessions-processed.log"

    try:
        # Claude Code extraction (skip when --cursor only is implied, but always run unless explicitly skipping)
        if not args.cursor:
            claude_projects = Path.home() / ".claude" / "projects"
            session_dirs = []
            if claude_projects.exists():
                for project_dir in claude_projects.iterdir():
                    if project_dir.is_dir() and not project_dir.name.startswith("."):
                        session_dirs.append(project_dir)
            count = extract_sessions(session_dirs, db, embedder, processed_log)
            if count > 0:
                print(f"Extracted {count} new Claude Code session(s)", file=sys.stderr)

        # Cursor extraction — always runs (--cursor flag is additive, not exclusive)
        cursor_count = extract_cursor_sessions(db, embedder, processed_log)
        if cursor_count > 0:
            print(f"Extracted {cursor_count} new Cursor conversation(s)", file=sys.stderr)
    finally:
        db.close()


if __name__ == "__main__":
    main()
