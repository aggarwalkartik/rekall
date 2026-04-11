# Rekall

**A second brain that builds itself.**

Your AI tools forget everything between sessions. Rekall fixes that. It extracts knowledge from your conversations automatically, embeds it locally, and makes it searchable by meaning. Next time you ask about something you've discussed before, it's already there.

```
You: "What did I decide about hosting?"

Rekall recalls:
  - Chose Cloudflare Pages over Vercel for free tier and edge deployment (decision, 0.85)
  - Vercel has better Next.js integration but charges for bandwidth (research, 0.72)
```

Works with Claude Code, Cursor, and Windsurf. One MCP server, all your tools share the same memory.

## Get started

```bash
git clone https://github.com/aggarwalkartik/rekall
cd rekall
uv run rekall
```

Add to your tool's MCP config:

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

That's it. Your AI tools now have persistent memory.

## What happens next

**Claude Code** - A startup hook extracts your past sessions automatically. Every conversation you've ever had becomes searchable on first run.

**Cursor** - The MCP server extracts your full Cursor history in the background when it starts. Sidebar chats, composer, agent mode - all of it.

**Both tools** - `recall` searches by meaning, not keywords. Ask about "pricing strategy" and it finds your research on "tiered service packages" even though those words never overlap.

## How it's different

Most AI memory tools (mem0, Engram) store what the LLM extracts. [A mem0 audit found 97.8% of extracted memories were junk.](https://github.com/mem0ai/mem0/issues/4573) Rekall stores your conversations verbatim and lets the embedding layer find what's relevant. Better retrieval, zero noise.

What Rekall adds that others don't:

- **Confidence decay** - memories fade over time unless reinforced. A pattern seen once fades in weeks. One confirmed 9 times lasts months.
- **Contradiction detection** - conflicting preferences get flagged, not silently applied.
- **Cross-tool memory** - Claude Code and Cursor share the same knowledge base. Switch tools, keep context.
- **Automatic extraction** - no "remember this" needed. Your conversations are mined on startup.

## Tools

The MCP server exposes four tools:

| Tool | What it does |
|---|---|
| `recall` | Search memories by meaning. Hybrid keyword + semantic search. |
| `remember` | Store a fact, preference, or decision. Deduplicates automatically. |
| `forget` | Archive a memory. Soft-delete, recoverable. |
| `list_memories` | Browse by type, project, or status. |

## Under the hood

- **SQLite** with FTS5 (keyword) + sqlite-vec (384-dim vectors). Hybrid results ranked by Reciprocal Rank Fusion.
- **bge-small-en-v1.5** via fastembed. Runs locally on CPU, no API key, ~50ms per embedding.
- **MEMORY.md** compiled on startup from high-confidence instincts. Injected into context so your AI already knows your preferences.
- **Obsidian sync** optional. `rekall-sync --vault /path/to/vault` exports memories as markdown notes.

## Commands

| Command | What it does |
|---|---|
| `rekall` | Start the MCP server |
| `rekall-extract` | Extract past sessions (add `--cursor` for Cursor only) |
| `rekall-compile` | Compile MEMORY.md from active instincts |
| `rekall-migrate` | Import v2 instincts and/or Obsidian vault |
| `rekall-backup` | Hot backup the database |
| `rekall-sync` | Export memories to Obsidian vault |

## Migrating from v2

```bash
uv run rekall-migrate --instincts /path/to/instincts.jsonl --vault /path/to/vault
```

Both flags optional.

## License

MIT
