"""One-way sync: SQLite → Obsidian vault."""
from __future__ import annotations
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from rekall.schemas import Document, Memory
from rekall.storage import Storage

ACRONYMS = {
    "API", "SQL", "CSS", "HTML", "MCP", "ETL", "JSON", "REST", "URL",
    "CV", "PDF", "AI", "LLM", "TDD", "FTS", "NL", "EUR", "GDPR",
    "ONNX", "SDK", "CLI", "MPC", "SSE", "HTTP", "HTTPS", "OAuth",
    "AWS", "GCP", "UI", "UX", "YAML", "TOML", "WAL", "BM25",
}

TYPE_TO_FOLDER = {
    "research": "Research",
    "reference": "Research",
    "decision": "Decisions",
    "idea": "Ideas",
    "project": "Projects",
}
# "session" deliberately excluded — raw conversation chunks aren't useful as vault notes

TYPE_TO_TAG = {
    "research": "research",
    "reference": "reference",
    "decision": "decision",
    "idea": "idea",
    "project": "project",
}


def to_title_case(s: str) -> str:
    """Convert to Title Case, preserving known acronyms."""
    words = s.title().split()
    return " ".join(w.upper() if w.upper() in ACRONYMS else w for w in words)


def content_hash(text: str) -> str:
    """Hash content for change detection."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def document_to_markdown(doc: Document) -> str:
    """Convert a document to markdown with frontmatter and wikilinks."""
    now = datetime.now().strftime("%Y-%m-%d")
    tag = TYPE_TO_TAG.get(doc.type, doc.type)
    project_parent = f"Parent: [[{doc.project}]]" if doc.project else "Parent: [[Rekall]]"

    content = doc.content
    if not content.startswith("#"):
        content = f"# {doc.title}\n\n{project_parent}\n\n{content}"
    else:
        lines = content.split("\n", 1)
        rest = lines[1] if len(lines) > 1 else ""
        content = f"{lines[0]}\n\n{project_parent}\n{rest}"

    return f"""---
date: {doc.created_at[:10] if doc.created_at else now}
tags: [{tag}]
status: {doc.status}
summary: "{doc.title}"
source: rekall-sync
---

{content}
"""


def sync_to_vault(db: Storage, vault_path: Path) -> int:
    """Sync unsynced/changed documents and instincts to the Obsidian vault."""
    count = 0

    # --- Sync documents (skip sessions) ---
    for doc_type, folder in TYPE_TO_FOLDER.items():
        docs = db.list_documents(type=doc_type, limit=500)
        folder_path = vault_path / folder
        folder_path.mkdir(parents=True, exist_ok=True)

        for doc in docs:
            meta = json.loads(doc.meta) if doc.meta else {}
            current_hash = content_hash(doc.content)

            # Skip if synced and content unchanged
            if meta.get("synced_to_vault") and meta.get("sync_hash") == current_hash:
                continue

            title = to_title_case(doc.title)
            file_path = folder_path / f"{title}.md"

            md = document_to_markdown(doc)
            file_path.write_text(md, encoding="utf-8")

            meta["synced_to_vault"] = True
            meta["sync_hash"] = current_hash
            meta["vault_path"] = str(file_path)
            db.update_document_meta(doc.id, json.dumps(meta))
            count += 1

    # --- Sync instincts as a collected file in Research/ ---
    instincts = db.list_memories(type="instinct", limit=500)
    if instincts:
        unsynced = []
        for m in instincts:
            meta = json.loads(m.meta) if m.meta else {}
            if not meta.get("synced_to_vault"):
                unsynced.append(m)

        if unsynced:
            instincts_path = vault_path / "Research" / "Rekall Instincts.md"
            now = datetime.now().strftime("%Y-%m-%d")

            lines = [
                "---",
                f"date: {now}",
                "tags: [reference, knowledge-management]",
                "status: active",
                'summary: "Auto-generated collection of Rekall instincts and preferences"',
                "source: rekall-sync",
                "---",
                "",
                "# Rekall Instincts",
                "",
                "Parent: [[Rekall]]",
                "",
                "Auto-synced from Rekall's memory database.",
                "",
            ]

            groups: dict[str, list] = defaultdict(list)
            for mem in instincts:
                groups[mem.domain or "general"].append(mem)

            for domain in sorted(groups.keys()):
                lines.append(f"## {domain.replace('-', ' ').title()}")
                lines.append("")
                for mem in groups[domain]:
                    conf = f" (confidence: {mem.confidence})" if mem.confidence < 0.9 else ""
                    lines.append(f"- {mem.content}{conf}")
                lines.append("")

            instincts_path.parent.mkdir(parents=True, exist_ok=True)
            instincts_path.write_text("\n".join(lines), encoding="utf-8")

            for mem in unsynced:
                meta = json.loads(mem.meta) if mem.meta else {}
                meta["synced_to_vault"] = True
                db.update_memory_meta(mem.id, json.dumps(meta))
            count += len(unsynced)

    return count


def main():
    """Entry point for rekall-sync."""
    import argparse
    parser = argparse.ArgumentParser(description="Sync Rekall memories to Obsidian vault")
    parser.add_argument("--vault", type=Path, required=True, help="Path to Obsidian vault")
    args = parser.parse_args()

    from rekall.config import get_config
    config = get_config()
    db = Storage(config.db_path)
    db.initialize()

    try:
        count = sync_to_vault(db, args.vault)
        print(f"Synced {count} items to {args.vault}", file=sys.stderr)
    finally:
        db.close()


if __name__ == "__main__":
    main()
