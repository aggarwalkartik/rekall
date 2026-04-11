"""Migration from Rekall v2 (vault + instincts.jsonl) to v3 (SQLite)."""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

from rekall.embedder import Embedder, chunk_text
from rekall.schemas import Chunk, Document, Memory
from rekall.storage import Storage

FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)

FOLDER_TYPE_MAP = {
    "Research": "research",
    "Decisions": "decision",
    "Ideas": "idea",
    "Projects": "project",
    "Sessions": "session",
}


def strip_frontmatter(text: str) -> str:
    return FRONTMATTER_RE.sub("", text).strip()


def import_instincts(
    instincts_path: Path,
    db: Storage,
    embedder: Embedder | None,
) -> int:
    """Import instincts.jsonl into the memories table."""
    count = 0
    with open(instincts_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            inst = json.loads(line)
            mem = Memory(
                id=inst["id"],
                content=inst["pattern"],
                type="instinct",
                source=inst.get("source", "observed"),
                confidence=inst.get("confidence", 0.5),
                evidence_count=inst.get("evidence_count", 1),
                domain=inst.get("domain"),
                created_at=inst.get("created", ""),
                updated_at=inst.get("last_seen", ""),
                last_seen_at=inst.get("last_seen", ""),
                meta=json.dumps({"section": inst.get("section"), "imported_from": "instincts.jsonl"}),
            )
            if db.get_memory(inst["id"]):
                continue  # Skip already-imported instincts
            db.add_memory(mem)
            if embedder:
                try:
                    vec = embedder.embed(mem.content)
                    db.add_memory_vector(mem.id, vec)
                except Exception as e:
                    print(f"Warning: Failed to embed {mem.id}: {e}", file=sys.stderr)
            count += 1
    return count


def import_vault_notes(
    vault_path: Path,
    db: Storage,
    embedder: Embedder | None,
) -> int:
    """Import Obsidian vault notes into the documents table."""
    count = 0
    for folder, doc_type in FOLDER_TYPE_MAP.items():
        folder_path = vault_path / folder
        if not folder_path.exists():
            continue
        for md_file in sorted(folder_path.glob("*.md")):
            raw = md_file.read_text(encoding="utf-8")
            content = strip_frontmatter(raw)
            if not content or len(content) < 20:
                continue

            title = md_file.stem
            doc_id = db.next_document_id()

            doc = Document(
                id=doc_id,
                title=title,
                content=content,
                type=doc_type,
                source_path=str(md_file),
                meta=json.dumps({"imported_from": "vault", "folder": folder}),
            )

            text_chunks = chunk_text(content, prefix=f"type: {doc_type} | topic: {title}")
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
                    print(f"Warning: Failed to embed {title}: {e}", file=sys.stderr)

            count += 1
    return count


def main():
    """Entry point for rekall-migrate."""
    import argparse
    parser = argparse.ArgumentParser(description="Migrate Rekall v2 data to v3")
    parser.add_argument("--vault", type=Path, help="Path to Obsidian vault")
    parser.add_argument("--instincts", type=Path, help="Path to instincts.jsonl")
    args = parser.parse_args()

    from rekall.config import get_config
    config = get_config()
    db = Storage(config.db_path)
    db.initialize()

    try:
        embedder = Embedder(config.model_name)
    except Exception:
        print("Warning: Embedding model unavailable. Importing without embeddings.", file=sys.stderr)
        embedder = None

    total = 0
    try:
        if args.instincts:
            count = import_instincts(args.instincts, db, embedder)
            print(f"Imported {count} instincts", file=sys.stderr)
            total += count

        if args.vault:
            count = import_vault_notes(args.vault, db, embedder)
            print(f"Imported {count} vault notes", file=sys.stderr)
            total += count

        print(f"Migration complete. {total} items imported.", file=sys.stderr)
    finally:
        db.close()


if __name__ == "__main__":
    main()
