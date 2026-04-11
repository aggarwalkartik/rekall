# Rekall

**A personal AI memory layer that builds itself.**

Rekall gives your AI tools persistent memory across sessions. It extracts knowledge from your conversations automatically, stores it with semantic embeddings, and makes it searchable by meaning. Works with Claude Code, Cursor, and Windsurf via MCP.

---

## What it does

- **Recall** — hybrid search (keyword + semantic) finds relevant knowledge before you even ask
- **Remember** — store facts, preferences, and decisions with automatic deduplication
- **Extract** — automatically mines past conversations from Claude Code and Cursor
- **Compile** — generates `MEMORY.md` injected at session start with your preferences and instincts
- **Sync** — optionally exports memories to an Obsidian vault as human-readable notes

---

## Quick start

```bash
git clone https://github.com/aggarwalkartik/rekall
cd rekall
uv run rekall
```

First run downloads the embedding model (~130MB) and creates `~/.rekall/rekall.db`.

---

## MCP configuration

Add Rekall as an MCP server so your AI tool can use `recall`, `remember`, `forget`, and `list_memories`.

### Claude Code (`~/.claude/mcp.json`)

```json
{
  "mcpServers": {
    "rekall": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/rekall", "rekall"]
    }
  }
}
```

### Cursor (`~/.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "rekall": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/rekall", "rekall"]
    }
  }
}
```

### Windsurf (`~/.codeium/windsurf/mcp_config.json`)

```json
{
  "mcpServers": {
    "rekall": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/rekall", "rekall"]
    }
  }
}
```

Replace `/path/to/rekall` with wherever you cloned the repo.

---

## How conversation extraction works

### Claude Code

A SessionStart hook runs `rekall-extract` on every new session. It reads your past Claude Code conversations from `~/.claude/projects/`, filters noise, chunks meaningful exchanges, embeds them, and stores them in SQLite. Fully automatic.

### Cursor

When the MCP server starts (which happens when you open a project in Cursor), it spawns a background task that reads Cursor's conversation history from `state.vscdb`. Parses both sidebar chat and composer/agent conversations. First run extracts your full Cursor history. Subsequent runs only process new conversations.

### What gets extracted

Conversations are stored verbatim — no LLM summarization. The embedding layer makes them searchable by meaning. Short messages, tool outputs, and system messages are filtered as noise.

---

## Migration from v2

If you used Rekall v2 (Obsidian vault + `instincts.jsonl`):

```bash
uv run rekall-migrate --instincts /path/to/instincts.jsonl --vault /path/to/vault
```

Both flags are optional.

---

## How it works

```
Your AI tool ──MCP──► recall "pricing strategy"
                          │
                          ├─ FTS5 keyword search  ─┐
                          └─ Vector similarity     ─┴─► RRF rank ──► top results

rekall-compile ──► SQLite memories ──► MEMORY.md (injected at session start)
rekall-extract ──► Claude Code JSONL + Cursor .vscdb ──► embedded documents
```

**Storage**: SQLite with FTS5 (keyword search) and sqlite-vec (384-dim vector search). Results merged with Reciprocal Rank Fusion.

**Embeddings**: `bge-small-en-v1.5` via fastembed (ONNX Runtime). Runs locally on CPU, no API key needed.

**MEMORY.md**: Active instincts grouped by domain, filtered by exponential confidence decay. Contradictions surface as `[!conflict]` callouts.

**Obsidian sync**: `rekall-sync --vault /path/to/vault` exports memories as markdown notes with proper frontmatter, Title Case filenames, and wikilinks.

---

## Entry points

| Command | What it does |
|---|---|
| `rekall` | Start the MCP server |
| `rekall-extract` | Extract Claude Code sessions (also `--cursor` for Cursor only) |
| `rekall-compile` | Compile `MEMORY.md` from active instincts |
| `rekall-migrate` | Import v2 instincts and/or Obsidian vault |
| `rekall-backup` | Hot backup the database |
| `rekall-sync` | Export memories to an Obsidian vault |

---

## What carries over from v2

- **Confidence decay** — `effective = confidence × e^(-days / (60 × √evidence_count))`. Single observations fade fast. Well-confirmed patterns persist.
- **Contradiction detection** — Jaccard similarity + polarity-flip detection flags conflicting instincts in `MEMORY.md`.
- **Safety hooks** — secrets check and dangerous command check ship as Claude Code hooks.

---

## License

MIT
