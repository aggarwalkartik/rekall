# How Rekall Works

This document covers Rekall's internals: how sessions become knowledge, how memory persists, and what the hooks do. Read this if you want to understand the system, extend it, or debug it.

---

## 1. Session Logging Flow

Session logging is a two-phase pipeline: fast skeleton creation (no LLM), then intelligent extraction (LLM-powered, background).

### Phase 1: Skeleton Creation (SessionStart)

`compile-memory.sh` runs as a SessionStart hook. After compiling memory (section 2), it calls `session-logger.py`, which does the following:

1. **Reads `~/.claude/sessions-processed.log`** to get the set of already-logged session IDs.
2. **Scans `~/.claude/projects/*/`** for `.jsonl` session files across all project directories.
3. **Parses each unprocessed session** — pure file I/O, no LLM. Extracts:
   - First and last timestamps (used for time range and date grouping)
   - Session slug (Claude Code's auto-generated name)
   - User and assistant message counts
   - Files touched (parsed from `tool_use` blocks in assistant messages)
   - Working directory (used for project inference via `rekall-projects.json`)
4. **Skips short sessions** — anything under 5 messages gets marked as processed and ignored.
5. **Groups sessions by date**, writes skeleton notes to `Sessions/YYYY-MM-DD.md`. Each session gets a section with metadata and placeholder lines (`_pending deep extraction_`) for decisions, learnings, ideas, and open questions.
6. **Marks all parsed sessions as processed** by appending their IDs to `sessions-processed.log`.

### Phase 2: Deep Extraction (Background Agent)

After skeleton creation, `compile-memory.sh` checks for session notes with `deep-extract: pending` in frontmatter:

1. Counts pending notes with `grep -rl "deep-extract: pending"` in `Sessions/`.
2. If any exist, appends a "Pending Session Extractions" notice to `MEMORY.md`.
3. Claude sees this notice in its session context and dispatches a **background agent**.
4. The background agent reads each pending session note, finds the matching JSONL file, and extracts:
   - Decisions made
   - Things learned
   - Ideas discussed
   - Personal observations about the user
5. Fills in the skeleton sections, updates relevant project hubs with links, updates `About {Name}.md`, and flips frontmatter to `deep-extract: done`.

This two-phase design keeps SessionStart fast (skeletons take ~1 second for dozens of sessions) while still producing rich, linked notes.

---

## 2. Memory System

Rekall's memory system gives Claude persistent preferences and learned patterns across sessions.

### Source of Truth: `instincts.jsonl`

A JSONL file where each line is one learned pattern:

```json
{
  "id": "ins_001",
  "pattern": "The learned pattern or preference",
  "domain": "domain-tag",
  "confidence": 0.5,
  "evidence_count": 1,
  "last_seen": "2026-03-29",
  "created": "2026-03-29",
  "source": "observed",
  "section": "User Preferences"
}
```

**Key fields:**

| Field | Purpose |
|-------|---------|
| `confidence` | 0.0 to 0.9. Controls whether the instinct appears in compiled output. |
| `source` | `user-explicit` (user stated it directly) or `observed` (inferred from behavior). |
| `evidence_count` | How many times the pattern has been confirmed. |
| `last_seen` | Last date the pattern was relevant. Drives time-based decay. |

### Confidence Rules

- **0.9** — User explicitly stated the preference.
- **0.7** — Observed 3+ times without correction. Cap for `observed` source.
- **0.5** — Observed 1-2 times.
- **0.3** — Tentative, single interaction.
- **Correction** — Reduce by 0.1 when the user overrides the pattern.
- **Decay** — -0.05 per 30 days since `last_seen`.
- **Below 0.2** — Removed from compiled output (still in JSONL for archaeology).

### Compilation

`compile-memory.sh` runs on every SessionStart:

1. Reads `instincts.jsonl`, applies time-based decay to compute effective confidence.
2. Filters out entries below 0.2.
3. Groups by `section`, sorts by confidence descending.
4. Writes `MEMORY.md` with confidence markers: unmarked (>=0.7), `[M]` (0.4-0.7), `[L]` (<0.4).
5. Appends `AGENDA.md` content (if it exists) as a "Current Agenda" section.
6. Appends pending extraction notices (if any).

**MEMORY.md is auto-generated. Do not edit it directly.** Edit `instincts.jsonl` instead.

### Maintenance

`/instincts-review` is a slash command that lets you audit the memory system: review instincts by confidence, dismiss false patterns, confirm tentative ones, or adjust confidence manually.

---

## 3. Vault Linting

`vault-lint.sh` runs as a **PostToolUse** hook on every `Write` or `Edit` operation.

### Trigger Conditions

- Only fires on files inside the Obsidian Vault path (detected by exact prefix match against the configured vault path).
- Only lints `.md` files.
- Skips root-level special files: `Home.md`, `About {Name}.md`, `AGENDA.md`.

### Checks Performed

1. **Frontmatter exists** — file must start with `---`.
2. **Required fields present** — `date`, `tags`, `status`, `summary`.
3. **Status value valid** — must be one of: `active`, `stale`, `archived`.
4. **Tags in allowed list** — validates each tag against the allowed type tags (`project`, `research`, `reference`, `decision`, `idea`, `session`) and domain tags.
5. **At least one wikilink** — every note needs at least one `[[link]]`.
6. **Parent link on Research/Decision notes** — files in `Research/` or `Decisions/` must have a `Parent: [[Project Hub]]` line.
7. **Filename conventions** — warns if the filename looks like kebab-case instead of Title Case.

### Behavior

Non-blocking. Outputs warnings to stderr. The write still succeeds even if linting fails — this is intentional. Rekall should never prevent you from saving work.

---

## 4. Safety Hooks

Three hooks protect against common mistakes. Hooks avoid Python where possible to minimize per-call latency.

### `secrets-check.sh` — PreToolUse on Write/Edit

Scans the content being written for regex patterns matching common secret formats:

- `API_KEY`, `SECRET_KEY`, `API_SECRET`, `PASSWORD` assignments with 16+ char values
- `Bearer` tokens (20+ chars)
- AWS access keys (`AKIA...`)
- GitHub PATs (`ghp_...`)
- OpenAI keys (`sk-...`)
- Slack tokens (`xox[bpoas]-...`)

**Blocking** — exits with code 2 to prevent the write. Allowlisted extensions: `.md`, `.example`, `.template`, and paths containing `memory` or `CLAUDE`. Uses a single Python invocation that reads stdin JSON, extracts fields, and runs all regex checks.

### `dangerous-cmd-check.sh` — PreToolUse on Bash

Checks the command string against destructive patterns:

- `rm -rf /`, `rm -rf ~`, `rm -rf .`, `rm -rf *`
- `git push --force`, `git push -f` (suggests `--force-with-lease`)
- `git reset --hard`, `git clean -fd`
- `DROP TABLE`, `DROP DATABASE`, `TRUNCATE TABLE`
- Fork bombs, `mkfs`, `dd if=`, raw disk writes

**Blocking** — exits with code 2. Tells Claude to ask for explicit user confirmation. No Python — extracts the command from JSON using bash regex.

### `post-write.sh` — PostToolUse on Write/Edit

Combined hook that performs two checks in a single invocation (no Python spawn):

1. **File size** — If the written file exceeds 400 lines, outputs a warning. Skips non-code files.
2. **Vault linting** — If the file is inside the vault, checks frontmatter, tags, status, wikilinks, parent links, and filename conventions.

**Non-blocking** — warnings only. Replaced the previous `vault-lint.sh` and `file-size-check.sh` to cut per-write overhead from ~90ms to ~35ms.

---

## 5. Vault Structure

```
Obsidian Vault/
  Home.md              # Index. Links to all projects and ideas.
  About {Name}.md      # User profile. Built from conversation patterns.
  AGENDA.md            # Living session handoff doc. Read on startup.
  Projects/            # One hub per project.
  Research/            # Findings, reference material, how-tos.
  Decisions/           # Choices with context and consequences.
  Ideas/               # Rough thoughts, not yet a project.
  Sessions/            # Auto-generated daily logs.
```

### Folder Rules

| Folder | Contains | Every note must have |
|--------|----------|---------------------|
| `Projects/` | Hub notes — one per project, links to its research and decisions. | Sections for Research and Decisions linking to sub-notes. |
| `Research/` | API docs, market research, how-tos, comparisons. | `Parent: [[Project Hub]]` linking to its project. |
| `Decisions/` | Choices made ("we chose X over Y because Z") with context and consequences. | `Parent: [[Project Hub]]` linking to its project. |
| `Ideas/` | Sparks and rough concepts. Under one page. | At least one `[[wikilink]]` to a related note. |
| `Sessions/` | One file per day. Sections per session, auto-generated. | `deep-extract` frontmatter field (managed by the logger). |

### Root-Level Files

- **`Home.md`** — Updated only when adding a new project or idea. Not for research or decisions.
- **`About {Name}.md`** — Updated by deep extraction when personal observations are found in sessions.
- **`AGENDA.md`** — Living context doc. Appended to MEMORY.md on session start so Claude knows what you were working on. Updated by `/session-log`.

---

## 6. File Locations

| What | Where |
|------|-------|
| Vault | User-configured via `REKALL_VAULT_PATH` (default: `~/Obsidian Vault`) |
| Hooks | `~/.claude/hooks/` |
| Commands | `~/.claude/commands/` |
| Memory (instincts + compiled) | `~/.claude/rekall/memory/` |
| Settings | `~/.claude/settings.json` |
| MCP config | `~/.claude/mcp.json` |
| CLAUDE.md | `~/.claude/CLAUDE.md` |
| Project mappings | `~/.claude/rekall-projects.json` |
| Processed sessions log | `~/.claude/sessions-processed.log` |

The memory directory is at a stable, CWD-independent location. `compile-memory.sh` falls back to searching `~/.claude/projects/*/memory/` for legacy installs.

---

## 7. JSONL Session Format

Claude Code stores conversation history as JSONL files. Each session is one file at:

```
~/.claude/projects/{encoded-cwd}/{sessionId}.jsonl
```

Where `{encoded-cwd}` is the working directory with path separators and special characters replaced (e.g., `C--Users-jdoe-Projects-my-app`).

### Event Types

Each line is a JSON object with a `type` field:

| Type | Content | Used by Rekall |
|------|---------|----------------|
| `user` | User's message text | Yes — message counting, content extraction |
| `assistant` | Claude's response, including `tool_use` blocks | Yes — file path extraction, content extraction |
| `progress` | Streaming progress updates | No |
| `system` | System-level events | No |
| `file-history-snapshot` | Point-in-time file state | No |
| `last-prompt` | Final prompt state | No |

### Key Fields

- **`timestamp`** — ISO 8601. Used for date grouping and time range display.
- **`slug`** — Human-readable session name, auto-generated by Claude Code.
- **`cwd`** — Working directory at session start. Used for project inference.
- **`parentUuid`** — Links to the previous event, forming a linked list for conversation order.

### Assistant Message Structure

Assistant events contain a `message.content` array with blocks:

```json
{
  "type": "assistant",
  "message": {
    "content": [
      { "type": "text", "text": "..." },
      {
        "type": "tool_use",
        "name": "Edit",
        "input": {
          "file_path": "/path/to/file.py",
          "old_string": "...",
          "new_string": "..."
        }
      }
    ]
  }
}
```

`session-logger.py` extracts `file_path` and `path` fields from `tool_use` inputs to determine which files a session touched. It filters out Obsidian Vault and `.claude` paths to focus on project files.

### Subagent Files

Session directories may contain `subagent` subdirectories with their own JSONL files. `session-logger.py` explicitly skips these (`if "subagent" in str(jsonl_file)`) to avoid double-counting.
