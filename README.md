# Rekall

**Personal AI memory layer — not a note-taking tool.**

Rekall gives Claude persistent memory across sessions using SQLite + vector embeddings. Every conversation can recall what you've told it before, without repeating yourself. It runs as an MCP server.

---

## What it does

- **Remember** — store facts, preferences, and decisions as searchable memories
- **Recall** — hybrid search (keyword + semantic) surfaces relevant context before you ask
- **Compile** — generates `MEMORY.md` injected at session start, so Claude already knows your instincts
- **Extract** — mines past Claude Code sessions and stores them as documents
- **Migrate** — imports your v2 `instincts.jsonl` and Obsidian vault notes into v3 SQLite

---

## Quick start

```bash
# Run directly with uvx (no install)
uvx rekall

# Or with uv in a cloned repo
uv run rekall
```

Rekall stores everything under `~/.rekall/` by default:
- `~/.rekall/rekall.db` — SQLite database (memories + documents + vectors)
- `~/.rekall/backups/` — hot backups

---

## MCP configuration

Add Rekall as an MCP server so Claude can call `remember`, `recall`, `forget`, and `list`.

### Claude Code (`~/.claude/settings.json`)

```json
{
  "mcpServers": {
    "rekall": {
      "command": "uvx",
      "args": ["rekall"]
    }
  }
}
```

### Cursor (`~/.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "rekall": {
      "command": "uvx",
      "args": ["rekall"]
    }
  }
}
```

### Windsurf (`~/.codeium/windsurf/mcp_config.json`)

```json
{
  "mcpServers": {
    "rekall": {
      "command": "uvx",
      "args": ["rekall"]
    }
  }
}
```

---

## Migration from v2

If you were using Rekall v2 (vault + `instincts.jsonl`), migrate your data to v3 SQLite in one command:

```bash
rekall-migrate --instincts ~/.claude/projects/.../memory/instincts.jsonl --vault ~/path/to/vault
```

Both flags are optional — run with just `--instincts` if you don't want to import vault notes, or just `--vault` to skip instincts.

---

## How it works

```
Claude ──MCP──► rekall recall "X"
                    │
                    ├─ FTS5 keyword search  ─┐
                    └─ Vector similarity     ─┴─► hybrid rank ──► top-N results
                    
rekall-compile ──► reads memories from SQLite ──► writes MEMORY.md
rekall-extract ──► reads ~/.claude session JSONLs ──► stores as documents
```

**Storage**: SQLite with two virtual tables — `memories_fts` (FTS5) for keyword search and `vec_memories`/`vec_chunks` (sqlite-vec) for semantic search. Hybrid results are re-ranked by RRF (Reciprocal Rank Fusion).

**Embeddings**: `all-MiniLM-L6-v2` via `sentence-transformers`. 384-dimensional vectors. Runs locally, no API key required.

**MEMORY.md compilation**: Active instincts grouped by section, filtered by effective confidence (exponential decay). Conflicts surface as `[!conflict]` callouts for review.

**Session extraction**: Reads raw Claude Code session JSONL files, chunks conversations, embeds and stores them as searchable documents.

---

## Entry points

| Command | What it does |
|---|---|
| `rekall` | Start the MCP server |
| `rekall-extract` | Extract past Claude Code sessions into the database |
| `rekall-compile` | Compile `MEMORY.md` from active instincts |
| `rekall-migrate` | Import v2 instincts.jsonl and/or Obsidian vault notes |
| `rekall-backup` | Hot backup the database (`sqlite3.backup()`) |
| `rekall-sync` | Sync memories to/from a remote store (planned) |

---

## What carries over from v2

- **Confidence decay** — `effective = confidence × e^(-days / (60 × √evidence_count))`. Patterns seen once fade fast; patterns confirmed 9+ times decay at a third of the base rate.
- **Contradiction detection** — Jaccard similarity + polarity-flip detection flags conflicting instincts (e.g. "prefers X" vs "avoids X") as `[!conflict]` callouts in `MEMORY.md`.
- **Safety hooks** — secrets check and dangerous command check still ship as Claude Code hooks.

---

## License

MIT
