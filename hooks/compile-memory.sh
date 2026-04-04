#!/usr/bin/env bash
# compile-memory.sh — SessionStart hook
# Reads instincts.jsonl and compiles top-confidence entries into MEMORY.md.

set -euo pipefail

# --- Load config ---
CONFIG_FILE="$HOME/.claude/rekall.conf"
if [ -f "$CONFIG_FILE" ]; then
  # shellcheck source=/dev/null
  source "$CONFIG_FILE"
fi

VAULT_PATH="${REKALL_VAULT_PATH:-$HOME/Obsidian Vault}"
MEMORY_DIR="${REKALL_MEMORY_DIR:-}"
PYTHON="${REKALL_PYTHON:-}"

# Resolve Python if not set by config
if [ -z "$PYTHON" ]; then
  for cmd in python3 python; do
    if command -v "$cmd" > /dev/null 2>&1; then
      if "$cmd" -c 'import sys; sys.exit(0 if sys.version_info[0] >= 3 else 1)' 2>/dev/null; then
        PYTHON="$cmd"
        break
      fi
    fi
  done
fi

if [ -z "$PYTHON" ]; then
  printf "Rekall: Python 3 not found — skipping memory compile\n" >&2
  exit 0
fi

# Resolve memory directory if not set by config
if [ -z "$MEMORY_DIR" ]; then
  if [ -d "$HOME/.claude/rekall/memory" ]; then
    MEMORY_DIR="$HOME/.claude/rekall/memory"
  else
    MEMORY_DIR=$(find "$HOME/.claude/projects" -name "instincts.jsonl" -path "*/memory/*" -exec dirname {} \; 2>/dev/null | head -1)
  fi
fi

if [ -z "$MEMORY_DIR" ]; then
  exit 0
fi

JSONL_FILE="$MEMORY_DIR/instincts.jsonl"
MEMORY_FILE="$MEMORY_DIR/MEMORY.md"

# If no instincts file exists, skip
if [ ! -f "$JSONL_FILE" ]; then
  exit 0
fi

# Use Python to compile JSONL to Markdown
MEMORY_DIR_ESC="$MEMORY_DIR" "$PYTHON" << 'PYEOF'
import json
import os
from collections import defaultdict
from datetime import datetime

memory_dir = os.environ["MEMORY_DIR_ESC"]
jsonl_path = os.path.join(memory_dir, "instincts.jsonl")
memory_path = os.path.join(memory_dir, "MEMORY.md")

instincts = []
with open(jsonl_path, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            try:
                instincts.append(json.loads(line))
            except json.JSONDecodeError:
                continue

if not instincts:
    with open(memory_path, "w", encoding="utf-8") as f:
        f.write("# Memory\n\n_No instincts recorded yet._\n")
    raise SystemExit(0)

# Apply time-based decay: -0.05 per 30 days since last_seen
today = datetime.now().date()
for inst in instincts:
    last_seen_str = inst.get("last_seen") or today.strftime("%Y-%m-%d")
    last_seen = datetime.strptime(last_seen_str, "%Y-%m-%d").date()
    days_since = (today - last_seen).days
    decay = (days_since // 30) * 0.05
    inst["effective_confidence"] = max(0, inst["confidence"] - decay)

# Filter out entries below 0.2
instincts = [i for i in instincts if i["effective_confidence"] >= 0.2]

# Group by section
sections = defaultdict(list)
for inst in instincts:
    section = inst.get("section", "General")
    sections[section].append(inst)

# Sort each section by confidence descending
for section in sections:
    sections[section].sort(key=lambda x: x["effective_confidence"], reverse=True)

section_order = sorted(sections.keys())

lines = ["# Memory", ""]

for section_name in section_order:
    entries = sections[section_name]
    if not entries:
        continue
    lines.append(f"## {section_name}")
    for inst in entries:
        conf = inst["effective_confidence"]
        if conf >= 0.7:
            marker = ""
        elif conf >= 0.4:
            marker = " [M]"
        else:
            marker = " [L]"
        pattern = inst["pattern"]
        if ": " in pattern and len(pattern.split(": ")[0]) < 60:
            parts = pattern.split(": ", 1)
            lines.append(f"- **{parts[0].strip()}**{marker}: {parts[1]}")
        else:
            lines.append(f"- {pattern}{marker}")
    lines.append("")

output = "\n".join(lines)
with open(memory_path, "w", encoding="utf-8") as f:
    f.write(output)
PYEOF

# Append AGENDA.md content to session context if it exists
AGENDA_FILE="$VAULT_PATH/AGENDA.md"
if [ -f "$AGENDA_FILE" ]; then
  printf "\n## Current Agenda\n" >> "$MEMORY_FILE"
  tail -n +2 "$AGENDA_FILE" >> "$MEMORY_FILE"
fi

# Run session logger to create skeleton notes for unprocessed sessions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REKALL_VAULT_PATH="$VAULT_PATH" "$PYTHON" "$SCRIPT_DIR/session-logger.py" 2>&1 || true

# Check for pending deep extractions and append notice to MEMORY.md
if [ -d "$VAULT_PATH/Sessions" ]; then
  PENDING=$(grep -rl "deep-extract: pending" "$VAULT_PATH/Sessions/" 2>/dev/null | wc -l)
  PENDING=$(printf '%s' "$PENDING" | tr -d ' ')
  if [ "$PENDING" -gt 0 ]; then
    printf "\n## Pending Session Extractions\n" >> "$MEMORY_FILE"
    printf "%s session note(s) have \`deep-extract: pending\` in Sessions/. Dispatch a background agent to run deep extraction on these — read each skeleton note, find the matching session JSONL in ~/.claude/projects/, extract decisions/learnings/ideas/personal traits, fill in the skeleton sections, update project hubs, then change \`deep-extract: pending\` to \`deep-extract: done\`.\n" "$PENDING" >> "$MEMORY_FILE"
  fi
fi

exit 0
