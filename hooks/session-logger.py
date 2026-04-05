#!/usr/bin/env python3
"""
session-logger.py — Fast session parser for SessionStart hook.
Finds unprocessed Claude Code sessions, creates skeleton Obsidian notes.
No LLM needed — pure file parsing.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from collections import defaultdict

VAULT_PATH = Path(os.environ.get("REKALL_VAULT_PATH", os.path.expanduser("~/Obsidian Vault")))
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
    if not CLAUDE_PROJECTS.exists():
        return []

    sessions = []
    try:
        for project_dir in CLAUDE_PROJECTS.iterdir():
            if not project_dir.is_dir():
                continue
            try:
                for jsonl_file in project_dir.glob("*.jsonl"):
                    if "subagent" in str(jsonl_file):
                        continue
                    session_id = jsonl_file.stem
                    sessions.append({
                        "id": session_id,
                        "path": jsonl_file,
                        "project_dir": project_dir.name,
                    })
            except PermissionError:
                continue
    except PermissionError:
        pass

    return sessions


def _extract_user_text(entry):
    """Pull the real text from a user message, skip noise."""
    msg = entry.get("message", {})
    content = msg.get("content", "")
    if isinstance(content, list):
        text = " ".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    elif isinstance(content, str):
        text = content
    else:
        return ""
    text = text.strip()
    # Skip noise: empty, skill injections, command outputs, system messages
    if len(text) < 5:
        return ""
    noise_markers = [
        "Base directory for this skill",
        "local-command-stdout",
        "local-command-caveat",
        "<command-name>",
        "command-args",
        "## Instructions",
        "**Working directory:**",
    ]
    for marker in noise_markers:
        if marker in text:
            return ""
    return text


def _extract_assistant_text(entry):
    """Pull just the text blocks from an assistant message (skip tool_use, thinking)."""
    msg = entry.get("message", {})
    content = msg.get("content", [])
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            t = block.get("text", "").strip()
            if t:
                parts.append(t)
    return "\n".join(parts)


def _score_pair(user_text, assistant_text):
    """Score a user-message + assistant-response pair for interestingness."""
    import re
    score = 0

    # Decision signals
    if re.search(r'\b(chose|decided|go with|let\'s go|switch to|went with|instead of|prefer)\b', user_text, re.I):
        score += 4
    # Idea signals
    if re.search(r'\b(what if|could we|should we|how about|maybe we|what about|concept)\b', user_text, re.I):
        score += 3
    # Opinion/preference signals
    if re.search(r'\b(I like|I don\'t like|I prefer|I want|I think|looks good|looks bad|too much|too little)\b', user_text, re.I):
        score += 2
    # Learning pattern: short question + long answer
    if '?' in user_text and len(assistant_text) > 500 and len(user_text) < 200:
        score += 3
    # Long user message = usually something important
    score += min(len(user_text) / 150, 2)

    return score


def parse_session_fast(session_path):
    """Fast parse a session JSONL — extract metadata and top conversation highlights."""
    first_ts = None
    last_ts = None
    slug = None
    files_touched = set()
    user_message_count = 0
    assistant_message_count = 0
    project_cwd = None

    # Collect all events for pair extraction
    events = []

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
                events.append(("user", entry))
            elif entry_type == "assistant":
                assistant_message_count += 1
                events.append(("assistant", entry))
                msg = entry.get("message", {})
                content = msg.get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            inp = block.get("input", {})
                            fp = inp.get("file_path") or inp.get("path", "")
                            if fp and "Obsidian" not in fp and ".claude" not in fp:
                                files_touched.add(os.path.basename(fp))

    # Extract and score conversation pairs
    highlights = []
    for i, (etype, entry) in enumerate(events):
        if etype != "user":
            continue
        user_text = _extract_user_text(entry)
        if not user_text:
            continue
        # Find next assistant response
        assistant_text = ""
        for j in range(i + 1, min(i + 5, len(events))):
            if events[j][0] == "assistant":
                assistant_text = _extract_assistant_text(events[j][1])
                break
        score = _score_pair(user_text, assistant_text)
        if score >= 2:
            # Truncate for the note — just enough context
            preview = user_text[:200] + ("..." if len(user_text) > 200 else "")
            resp_preview = assistant_text[:300] + ("..." if len(assistant_text) > 300 else "")
            highlights.append((score, preview, resp_preview))

    # Sort by score, take top 5
    highlights.sort(key=lambda x: x[0], reverse=True)
    top_highlights = highlights[:5]

    return {
        "slug": slug or "unnamed-session",
        "first_ts": first_ts,
        "last_ts": last_ts,
        "user_messages": user_message_count,
        "assistant_messages": assistant_message_count,
        "total_messages": user_message_count + assistant_message_count,
        "files_touched": sorted(files_touched)[:20],
        "cwd": project_cwd,
        "highlights": top_highlights,
    }


def load_project_mappings():
    config_path = Path(os.path.expanduser("~/.claude/rekall-projects.json"))
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f).get("mappings", [])
        except (json.JSONDecodeError, PermissionError):
            return []
    return []


def prettify_name(name):
    """Turn a slug into a readable name. rekall -> Rekall, my-cool-app -> My Cool App."""
    import re
    # If it looks like a domain (has .com/.io/.dev etc), keep it as-is
    if re.search(r'\.\w{2,4}$', name):
        return name
    name = re.sub(r'[-_.]', ' ', name)
    words = []
    for w in name.split():
        if w.isupper() and len(w) > 1:
            words.append(w)  # Keep acronyms like API, CLI
        else:
            words.append(w.capitalize())
    return " ".join(words)


def name_from_git(directory):
    """Try to read the repo name from .git/config."""
    import re
    git_config = directory / ".git" / "config"
    if not git_config.exists():
        return None
    try:
        text = git_config.read_text(encoding="utf-8")
        match = re.search(r'url\s*=\s*.+[/:](.+?)(?:\.git)?\s*$', text, re.MULTILINE)
        if match:
            return prettify_name(match.group(1))
    except OSError:
        pass
    return None


def find_project_root(cwd_path):
    """Walk up from cwd looking for .git or common project markers."""
    markers = [".git", "package.json", "pyproject.toml", "Cargo.toml", "go.mod"]
    home = Path.home()
    path = cwd_path

    while path != home and path != path.parent:
        for marker in markers:
            if (path / marker).exists():
                return path
        path = path.parent

    return None


def infer_project_from_cwd(cwd):
    if not cwd:
        return None

    # 1. Manual overrides always win
    cwd_lower = cwd.lower().replace("\\", "/")
    for mapping in load_project_mappings():
        if mapping["pattern"].lower() in cwd_lower:
            return mapping["project"]

    # 2. Home directory = General
    cwd_path = Path(cwd)
    if cwd_path == Path.home():
        return "General"

    # 3. If directory still exists, walk up to find project root
    if cwd_path.exists():
        root = find_project_root(cwd_path)
        if root:
            # Try git remote name first, fall back to folder name
            git_name = name_from_git(root)
            if git_name:
                return git_name
            return prettify_name(root.name)

    # 4. Directory doesn't exist — use the last meaningful folder name from the path
    parts = [p for p in cwd_path.parts if p not in ("/", "Users", "home", Path.home().name)]
    if parts:
        return prettify_name(parts[-1])

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
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    note_path = SESSIONS_DIR / f"{date}.md"

    new_sections = []
    for entry in entries:
        project = infer_project_from_cwd(entry["cwd"])
        project_link = f"[[{project}]]" if project else "unknown project"
        time_range = f"{format_timestamp(entry['first_ts'])}\u2013{format_timestamp(entry['last_ts'])}"
        files_str = ", ".join(entry["files_touched"][:5]) if entry["files_touched"] else "none detected"

        # Build highlights section
        highlights = entry.get("highlights", [])
        if highlights:
            highlights_lines = "\n### Highlights\n"
            for _score, user_msg, resp_preview in highlights:
                # Clean up for markdown
                user_clean = user_msg.replace("\n", " ").strip()
                highlights_lines += f"\n> **{user_clean}**\n"
                if resp_preview:
                    resp_first = resp_preview.split("\n")[0].strip()
                    if resp_first:
                        highlights_lines += f"> {resp_first}\n"
            extract_note = "\n_Highlights auto-extracted. Run deep extraction for full analysis._\n"
        else:
            highlights_lines = ""
            extract_note = "\n_No highlights detected. Run deep extraction for full analysis._\n"

        section = f"""## Session \u2014 {format_timestamp(entry['first_ts'])} ({entry['slug']})

- **Time**: {time_range}
- **Project**: {project_link}
- **Messages**: {entry['total_messages']} ({entry['user_messages']} user, {entry['assistant_messages']} assistant)
- **Files touched**: {files_str}
{highlights_lines}{extract_note}"""
        new_sections.append(section)

    if note_path.exists():
        existing = note_path.read_text(encoding="utf-8")
        # Skip sections whose session slug is already in the note (prevent duplicates)
        filtered = []
        for section in new_sections:
            # Extract slug from the section header line
            first_line = section.strip().split("\n")[0]
            if first_line not in existing:
                filtered.append(section)
        if not filtered:
            return
        # Reset deep-extract to pending if new sessions were appended
        existing = existing.replace("deep-extract: done", "deep-extract: pending")
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(existing.rstrip() + "\n\n" + "\n".join(filtered))
    else:
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

    unprocessed = [s for s in all_sessions if s["id"] not in processed]

    if not unprocessed:
        return

    parsed = []
    skipped = 0
    for session in unprocessed:
        try:
            meta = parse_session_fast(session["path"])
        except (PermissionError, OSError):
            continue
        if meta["total_messages"] < 5:
            skipped += 1
            mark_processed([session["id"]])
            continue
        meta["session_id"] = session["id"]
        parsed.append(meta)

    if not parsed:
        return

    by_date = defaultdict(list)
    for p in parsed:
        date = get_date_from_ts(p["first_ts"])
        by_date[date].append(p)

    total_logged = 0
    for date, entries in sorted(by_date.items()):
        write_skeleton_note(date, entries)
        total_logged += len(entries)

    mark_processed([p["session_id"] for p in parsed])

    dates = sorted(by_date.keys())
    date_range = dates[0] if len(dates) == 1 else f"{dates[0]} to {dates[-1]}"
    print(f"Session logger: {total_logged} session(s) logged ({date_range}). Deep extraction pending.", file=sys.stderr)
    if skipped:
        print(f"  Skipped {skipped} short session(s) (<5 messages).", file=sys.stderr)


if __name__ == "__main__":
    main()
