"""Rekall MCP Server — personal AI memory layer."""
from __future__ import annotations
import hashlib
import json
import math
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncIterator

from mcp.server.fastmcp import FastMCP

from rekall.config import get_config
from rekall.embedder import Embedder, chunk_text
from rekall.schemas import Chunk, Document, Memory
from rekall.storage import Storage


@dataclass
class AppContext:
    db: Storage
    embedder: Embedder | None


def create_app() -> FastMCP:
    """Create the MCP server with all tools registered."""

    @asynccontextmanager
    async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
        config = get_config()
        db = Storage(config.db_path)
        db.initialize()
        embedder: Embedder | None
        try:
            embedder = Embedder(config.model_name)
            # Warm up model
            embedder.embed("warmup")
        except Exception as e:
            print(
                f"Warning: Embedding model unavailable: {e}. Search is keyword-only.",
                file=sys.stderr,
            )
            embedder = None
        try:
            yield AppContext(db=db, embedder=embedder)
        finally:
            db.close()

    mcp = FastMCP(
        "rekall",
        lifespan=app_lifespan,
    )

    @mcp.tool(
        description=(
            "Search your personal knowledge base for relevant memories, decisions, "
            "research, and past conversations. Use this FIRST before web search to "
            "check if you already have knowledge on this topic."
        )
    )
    def recall(
        query: str,
        limit: int = 5,
        type: str | None = None,
        project: str | None = None,
    ) -> str:
        """Search memories by meaning and keywords."""
        ctx: AppContext = mcp.get_context().request_context.lifespan_context

        if ctx.embedder:
            query_vec = ctx.embedder.embed(query)
            results = ctx.db.hybrid_search(
                query_text=query,
                query_embedding=query_vec,
                limit=limit,
                type_filter=type,
                project_filter=project,
            )
        else:
            # Fallback: BM25 only
            mem_results = ctx.db.fts_search_memories(query, limit=limit)
            fallback = [
                {
                    "id": m.id,
                    "content": m.content,
                    "type": m.type,
                    "confidence": m.confidence,
                    "score": 0.0,
                    "source_document": None,
                    "source_title": None,
                }
                for m in mem_results
            ]
            return json.dumps(fallback, indent=2)

        # Apply confidence decay to memory results (only for full Memory records)
        now = datetime.now()
        filtered = []
        for r in results:
            if r.source_document is None:
                # This is a memory result — apply decay
                mem = ctx.db.get_memory(r.id)
                if mem and r.confidence is not None:
                    last_seen = datetime.fromisoformat(mem.last_seen_at)
                    days_since = (now - last_seen).days
                    evidence = mem.evidence_count
                    effective = r.confidence * math.exp(
                        -days_since / (60 * math.sqrt(max(evidence, 1)))
                    )
                    if effective < 0.2:
                        continue
                    r.confidence = round(effective, 2)
            filtered.append(r)

        # Truncate to token budget (~2000 tokens / 8000 chars)
        output = []
        total_chars = 0
        for r in filtered:
            content = r.content
            if total_chars + len(content) > 8000:
                remaining = 8000 - total_chars
                if remaining > 200:
                    content = content[:remaining] + "..."
                    entry = r.model_dump()
                    entry["content"] = content
                    output.append(entry)
                break
            total_chars += len(content)
            output.append(r.model_dump())

        return json.dumps(output, indent=2)

    @mcp.tool(
        description=(
            "Store a piece of knowledge, preference, decision, or fact for future "
            "recall. Deduplicates automatically — if this knowledge already exists, "
            "it will be reinforced instead of duplicated. Set metadata.source to "
            "'user-explicit' when the user directly states something, or 'observed' "
            "when you infer it from behavior."
        )
    )
    def remember(
        text: str,
        type: str = "fact",
        metadata: dict | None = None,
    ) -> str:
        """Store a memory with automatic dedup."""
        ctx: AppContext = mcp.get_context().request_context.lifespan_context
        metadata = metadata or {}

        # Determine confidence from source
        source = metadata.get("source", None)
        if source == "user-explicit":
            confidence = 0.9
        elif source == "observed":
            confidence = 0.5
        else:
            confidence = 0.7

        # Check for exact duplicate via content hash
        content_hash = hashlib.sha256(text.strip().lower().encode()).hexdigest()[:16]
        existing_id = ctx.db.memory_content_hash_exists(content_hash)
        if existing_id:
            ctx.db.bump_evidence(existing_id)
            return json.dumps(
                {
                    "status": "reinforced",
                    "memory_id": existing_id,
                    "message": "Existing memory reinforced (exact match)",
                }
            )

        # Check for semantic duplicate via embedding
        query_vec = None
        if ctx.embedder:
            query_vec = ctx.embedder.embed(text)
            similar = ctx.db.vec_search_memories(query_vec, limit=3)
            for mem_id, distance in similar:
                # sqlite-vec returns cosine distance; similarity = 1 - distance
                similarity = 1.0 - distance
                if similarity > 0.90:
                    ctx.db.bump_evidence(mem_id)
                    return json.dumps(
                        {
                            "status": "reinforced",
                            "memory_id": mem_id,
                            "message": "Existing memory reinforced (semantic match)",
                        }
                    )

        # Route long content to documents
        if len(text) > 2048:
            doc_id = ctx.db.next_document_id()
            doc_type = "reference" if type == "fact" else type
            doc = Document(
                id=doc_id,
                title=text[:80].strip(),
                content=text,
                type=doc_type,
                project=metadata.get("project"),
            )
            chunks_text = chunk_text(text, prefix=f"type: {doc_type}")
            chunks = [
                Chunk(
                    chunk_id=f"{doc_id}_chk_{i:03d}",
                    document_id=doc_id,
                    content=c,
                    chunk_index=i,
                )
                for i, c in enumerate(chunks_text)
            ]
            ctx.db.add_document(doc, chunks)
            if ctx.embedder:
                vecs = ctx.embedder.embed_batch([c.content for c in chunks])
                for chunk, vec in zip(chunks, vecs):
                    ctx.db.add_chunk_vector(chunk.chunk_id, vec)
            return json.dumps(
                {
                    "status": "stored",
                    "document_id": doc_id,
                    "chunks": len(chunks),
                    "message": "Stored as document with chunks",
                }
            )

        # Store as atomic memory
        mem_id = ctx.db.next_memory_id()
        meta_json = json.dumps({"content_hash": content_hash, **metadata})
        mem = Memory(
            id=mem_id,
            content=text,
            type=type,
            source=source,
            confidence=confidence,
            domain=metadata.get("domain"),
            project=metadata.get("project"),
            meta=meta_json,
        )
        ctx.db.add_memory(mem)
        if ctx.embedder and query_vec is not None:
            ctx.db.add_memory_vector(mem_id, query_vec)

        return json.dumps({"status": "stored", "memory_id": mem_id})

    @mcp.tool(
        description=(
            "Remove a memory from active recall. The memory is archived, not "
            "permanently deleted — it can be recovered if needed."
        )
    )
    def forget(memory_id: str) -> str:
        """Soft-delete a memory."""
        ctx: AppContext = mcp.get_context().request_context.lifespan_context
        mem = ctx.db.get_memory(memory_id)
        if not mem:
            return json.dumps({"error": f"Memory {memory_id} not found"})
        ctx.db.soft_delete_memory(memory_id)
        ctx.db.remove_memory_vector(memory_id)
        return json.dumps({"status": "forgotten", "memory_id": memory_id})

    @mcp.tool(
        name="list_memories",
        description=(
            "Browse memories by type, project, or status. Use this when you need to "
            "see all memories of a kind (e.g., all instincts, all decisions for a "
            "project) rather than searching for something specific."
        ),
    )
    def list_memories(
        type: str | None = None,
        project: str | None = None,
        status: str = "active",
        limit: int = 20,
    ) -> str:
        """Browse/filter memories."""
        ctx: AppContext = mcp.get_context().request_context.lifespan_context
        results = ctx.db.list_memories(
            type=type, project=project, status=status, limit=limit
        )
        return json.dumps([m.model_dump() for m in results], indent=2)

    return mcp


def main():
    app = create_app()
    app.run()


if __name__ == "__main__":
    main()
