#!/usr/bin/env python3
"""
session-logger.py — Fast session parser for SessionStart hook.
Finds unprocessed Claude Code sessions, creates skeleton Obsidian notes.
No LLM needed — pure file parsing.
"""

import json
import os
import sys
import glob
from datetime import datetime
from pathlib import Path
from collections import defaultdict

VAULT_PATH = Path(os.environ.get("REKALL_VAULT_PATH", os.path.expanduser("~/Documents/Obsidian Vault")))
SESSIONS_DIR = VAULT_PATH / "Sessions"
PROCESSED_LOG = Path(os.path.expanduser("~/.claude/sessions-processed.log"))
CLAUDE_PROJECTS = Path(os.path.expanduser("~/.claude/projects"))

def get_processed_sessions():
    """Read set of already-processed session IDs."""
    if not PROCESSED_LOG.exists():
        return set()
    return set(PROCESSED_LOG.read_text(encoding="utf-8").strip().splitlines())

def mark_processed(session_ids):
    """Append session IDs to the processed log."""
    with open(PROCESSED_LOG, "a", encoding="utf-8") as f:
        for sid in session_ids:
            f.write(sid + "\n")

def find_session_files():
    """Find all session JSONL files across all projects."""
    sessions = []
    for project_dir in CLAUDE_PROJECTS.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl_file in project_dir.glob("*.jsonl"):
            # Skip files in subagent directories
            if "subagent" in str(jsonl_file):
                continue
            session_id = jsonl_file.stem
            sessions.append({
                "id": session_id,
                "path": jsonl_file,
                "project_dir": project_dir.name,
            })
    return sessions

def parse_session_fast(session_path):
    """Fast parse a session JSONL — extract metadata without LLM."""
    messages = []
    first_ts = None
    last_ts = None
    slug = None
    files_touched = set()
    user_message_count = 0
    assistant_message_count = 0
    project_cwd = None

    with open(session_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            ts = entry.get("timestamp")
            if ts:
                if first_ts is None:
                    first_ts = ts
                last_ts = ts

            if not slug and entry.get("slug"):
                slug = entry["slug"]

            if not project_cwd and entry.get("cwd"):
                project_cwd = entry["cwd"]

            entry_type = entry.get("type")
            if entry_type == "user":
                user_message_count += 1
            elif entry_type == "assistant":
                assistant_message_count += 1
                # Extract file paths from tool_use blocks
                msg = entry.get("message", {})
                content = msg.get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            inp = block.get("input", {})
                            fp = inp.get("file_path") or inp.get("path", "")
                            if fp and "Obsidian" not in fp and ".claude" not in fp:
                                # Normalize to just filename
                                files_touched.add(os.path.basename(fp))
                            cmd = inp.get("command", "")
                            if cmd:
                                # Extract project signals from commands
                                pass

    return {
        "slug": slug or "unnamed-session",
        "first_ts": first_ts,
        "last_ts": last_ts,
        "user_messages": user_message_count,
        "assistant_messages": assistant_message_count,
        "total_messages": user_message_count + assistant_message_count,
        "files_touched": sorted(files_touched)[:20],  # Cap at 20
        "cwd": project_cwd,
    }

def load_project_mappings():
    config_path = Path(os.path.expanduser("~/.claude/rekall-projects.json"))
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f).get("mappings", [])
    return []

def infer_project_from_cwd(cwd):
    if not cwd:
        return None
    cwd_lower = cwd.lower().replace("\\", "/")
    for mapping in load_project_mappings():
        if mapping["pattern"].lower() in cwd_lower:
            return mapping["project"]
    return None

def format_timestamp(ts_str):
    """Parse ISO timestamp to readable format."""
    if not ts_str:
        return "unknown"
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.strftime("%H:%M")
    except (ValueError, TypeError):
        return "unknown"

def get_date_from_ts(ts_str):
    """Extract YYYY-MM-DD from timestamp."""
    if not ts_str:
        return datetime.now().strftime("%Y-%m-%d")
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return datetime.now().strftime("%Y-%m-%d")

def write_skeleton_note(date, entries):
    """Write or append skeleton session note for a given date."""
    SESSIONS_DIR.mkdir(exist_ok=True)
    note_path = SESSIONS_DIR / f"{date}.md"

    new_sections = []
    for entry in entries:
        project = infer_project_from_cwd(entry["cwd"])
        project_link = f"[[{project}]]" if project else "unknown project"
        time_range = f"{format_timestamp(entry['first_ts'])}\u2013{format_timestamp(entry['last_ts'])}"
        files_str = ", ".join(entry["files_touched"][:5]) if entry["files_touched"] else "none detected"

        section = f"""## Session \u2014 {format_timestamp(entry['first_ts'])} ({entry['slug']})

- **Time**: {time_range}
- **Project**: {project_link}
- **Messages**: {entry['total_messages']} ({entry['user_messages']} user, {entry['assistant_messages']} assistant)
- **Files touched**: {files_str}

### Decisions Made
_pending deep extraction_

### Learned
_pending deep extraction_

### Ideas
_pending deep extraction_

### Open Questions
_pending deep extraction_
"""
        new_sections.append(section)

    if note_path.exists():
        # Append to existing note
        existing = note_path.read_text(encoding="utf-8")
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(existing.rstrip() + "\n\n" + "\n".join(new_sections))
    else:
        # Create new note with frontmatter
        frontmatter = f"""---
date: {date}
tags: [session]
status: active
summary: "Session log for {date}"
deep-extract: pending
---

# Sessions \u2014 {date}

"""
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(frontmatter + "\n".join(new_sections))

def main():
    processed = get_processed_sessions()
    all_sessions = find_session_files()

    # Filter to unprocessed
    unprocessed = [s for s in all_sessions if s["id"] not in processed]

    if not unprocessed:
        return

    # Parse each session
    parsed = []
    skipped = 0
    for session in unprocessed:
        meta = parse_session_fast(session["path"])
        if meta["total_messages"] < 5:
            skipped += 1
            # Still mark as processed so we don't re-check
            mark_processed([session["id"]])
            continue
        meta["session_id"] = session["id"]
        parsed.append(meta)

    if not parsed:
        return

    # Group by date
    by_date = defaultdict(list)
    for p in parsed:
        date = get_date_from_ts(p["first_ts"])
        by_date[date].append(p)

    # Write skeleton notes
    total_logged = 0
    for date, entries in sorted(by_date.items()):
        write_skeleton_note(date, entries)
        total_logged += len(entries)

    # Mark all as processed
    mark_processed([p["session_id"] for p in parsed])

    # Output status for the hook
    dates = sorted(by_date.keys())
    date_range = dates[0] if len(dates) == 1 else f"{dates[0]} to {dates[-1]}"
    print(f"Session logger: {total_logged} session(s) logged ({date_range}). Deep extraction pending.", file=sys.stderr)
    if skipped:
        print(f"  Skipped {skipped} short session(s) (<5 messages).", file=sys.stderr)

if __name__ == "__main__":
    main()
