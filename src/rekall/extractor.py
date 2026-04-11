"""Session extraction pipeline — parse Claude Code JSONL sessions into memories."""
from __future__ import annotations
import json
import os
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


def main():
    """Entry point for rekall-extract. Use --background to run in background."""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--background", action="store_true")
    args = parser.parse_args()

    if args.background:
        # Fork to background
        if os.name == "nt":
            # Windows: use subprocess
            subprocess.Popen(
                [sys.executable, "-m", "rekall.extractor"],
                creationflags=subprocess.DETACHED_PROCESS,
                stdout=subprocess.DEVNULL,
                stderr=open(Path.home() / ".rekall" / "extract.log", "a"),
            )
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

    # Find all session directories
    claude_projects = Path.home() / ".claude" / "projects"
    session_dirs = []
    if claude_projects.exists():
        for project_dir in claude_projects.iterdir():
            if project_dir.is_dir() and not project_dir.name.startswith("."):
                session_dirs.append(project_dir)

    processed_log = config.data_dir / "sessions-processed.log"

    try:
        count = extract_sessions(session_dirs, db, embedder, processed_log)
        if count > 0:
            print(f"Extracted {count} new session(s)", file=sys.stderr)
    finally:
        db.close()


if __name__ == "__main__":
    main()
