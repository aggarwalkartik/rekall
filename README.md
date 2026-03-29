# Rekall

**A second brain that builds itself.**

Rekall turns your Claude Code conversation history into a structured Obsidian knowledge base — automatically. No manual logging, no copy-paste, no plugins. Every session you've ever had becomes searchable, linked knowledge.

## What it does

Rekall works in three layers.

**Bootstrap** — Run setup once. Rekall mines your entire Claude Code history and creates notes for decisions, learnings, ideas, and a profile of who you are.

**Autopilot** — Every time you start Claude Code, new sessions are logged automatically. Your vault grows as you work. Zero manual steps.

**Intelligence** — Slash commands for deeper work. Vault health audits find broken links and orphaned knowledge. Synthesis turns scattered research into coherent frameworks. A memory system tracks your preferences and decays stale ones.

## Quick start

```bash
git clone https://github.com/aggarwalkartik/rekall
cd rekall
./setup.sh          # Unix/Mac
# or
.\setup.ps1         # Windows
```

Then start a new Claude Code session. That's it.

## What you get

Setup creates a vault structure designed for long-term knowledge accumulation.

| Folder / File | Purpose |
|---|---|
| `Projects/` | One hub per project. Links to its research and decisions. |
| `Research/` | Findings, how-tos, API docs, comparisons. |
| `Decisions/` | Choices made with context and consequences. |
| `Ideas/` | Sparks and rough thoughts. |
| `Sessions/` | Auto-generated daily logs from Claude Code conversations. |
| `AGENDA.md` | Session handoff context, auto-updated. |
| `About {You}.md` | Your profile, built from conversation patterns. |

## How it works

1. Setup copies hooks, commands, and a vault template to your system.
2. On first session, `session-logger.py` discovers all past sessions and creates skeleton notes.
3. Claude reads "pending extractions" in context and dispatches a background agent to fill in details.
4. Every subsequent session is auto-logged on next startup.
5. A vault linter catches formatting issues in real-time.
6. Safety hooks block accidental secret leaks and destructive commands.

## Commands

| Command | What it does |
|---|---|
| `/session-log` | Manually capture the current session (auto-logging handles past sessions) |
| `/vault-health` | Audit vault: orphans, broken links, stale notes, health score out of 100 |
| `/vault-consolidate {project}` | Synthesize all research for a project into one framework note |
| `/instincts-review` | Review your memory system — confirm, dismiss, or adjust learned patterns |

## Hooks

| Hook | Type | What it does |
|---|---|---|
| `session-logger.py` | SessionStart | Auto-logs unprocessed sessions as vault notes |
| `compile-memory.sh` | SessionStart | Compiles preferences + agenda into session context |
| `vault-lint.sh` | PostToolUse | Warns on missing frontmatter, bad tags, orphan notes |
| `secrets-check.sh` | PreToolUse | Blocks writes containing API keys or credentials |
| `dangerous-cmd-check.sh` | PreToolUse | Blocks destructive shell commands (`rm -rf`, force push) |
| `file-size-check.sh` | PostToolUse | Warns when files exceed 400 lines |

## Customization

**Domain tags** — Edit the allowed tags list in your `~/.claude/CLAUDE.md`.

**Project mappings** — Edit `~/.claude/rekall-projects.json` to map directories to project names.

**Note templates** — Modify the templates in `CLAUDE.md` to match your style.

**Commands** — All commands are markdown files in `~/.claude/commands/`. Edit freely.

## Existing vaults

Rekall is safe for existing Obsidian vaults. Setup creates folders only if they don't exist, appends to `CLAUDE.md` (never overwrites), and merges into `settings.json`. Your existing notes, plugins, and configuration are untouched.

## FAQ

**Does it send data anywhere?**
No. Everything stays on your machine. Rekall is just files — hooks, commands, and markdown.

**Does it need an API key?**
No. It runs inside Claude Code, which handles authentication.

**Does it work with existing vaults?**
Yes. Setup skips existing folders and files.

**What if I stop using it?**
Your vault is plain markdown. It works with or without Rekall, Claude Code, or Obsidian.

**What Claude Code plan do I need?**
Any plan that supports Claude Code (Pro, Max, or Team).

## License

MIT
