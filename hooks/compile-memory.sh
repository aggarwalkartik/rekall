#!/usr/bin/env bash
# compile-memory.sh — SessionStart hook
# Reads instincts.jsonl and compiles top-confidence entries into MEMORY.md.

set -euo pipefail

# Auto-detect memory directory — find first project with instincts.jsonl
MEMORY_DIR=$(find "$HOME/.claude/projects" -name "instincts.jsonl" -path "*/memory/*" -exec dirname {} \; 2>/dev/null | head -1)
if [ -z "$MEMORY_DIR" ]; then
  # No memory dir found yet — create one for current project
  CWD_ENCODED=$(pwd | sed 's/[^a-zA-Z0-9]/-/g')
  MEMORY_DIR="$HOME/.claude/projects/$CWD_ENCODED/memory"
  mkdir -p "$MEMORY_DIR"
fi

JSONL_FILE="$MEMORY_DIR/instincts.jsonl"
MEMORY_FILE="$MEMORY_DIR/MEMORY.md"

# If no instincts file exists, skip
if [ ! -f "$JSONL_FILE" ]; then
  exit 0
fi

# Use Python to compile JSONL to Markdown
MEMORY_DIR_ESC="$MEMORY_DIR" python << 'PYEOF'
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

# Apply time-based decay: -0.05 per 30 days since last_seen
today = datetime.now().date()
for inst in instincts:
    last_seen = datetime.strptime(inst.get("last_seen", "2026-03-22"), "%Y-%m-%d").date()
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

# Collect all unique section names, output in order of first appearance
section_order = []
seen = set()
for inst_list in sections.values():
    for inst in inst_list:
        s = inst.get("section", "General")
        if s not in seen:
            section_order.append(s)
            seen.add(s)
section_order.sort()

lines = ["# Memory", ""]

for section_name in section_order:
    if section_name not in sections:
        continue
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

VAULT_PATH="${REKALL_VAULT_PATH:-$HOME/Documents/Obsidian Vault}"

# Append AGENDA.md content to session context if it exists
AGENDA_FILE="$VAULT_PATH/AGENDA.md"
if [ -f "$AGENDA_FILE" ]; then
  echo "" >> "$MEMORY_FILE"
  echo "## Current Agenda" >> "$MEMORY_FILE"
  # Skip the H1 title line, include the rest
  tail -n +2 "$AGENDA_FILE" >> "$MEMORY_FILE"
fi

# Run session logger to create skeleton notes for unprocessed sessions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python "$SCRIPT_DIR/session-logger.py" 2>&1

# Check for pending deep extractions and append notice to MEMORY.md
PENDING=$(grep -rl "deep-extract: pending" "$VAULT_PATH/Sessions/" 2>/dev/null | wc -l)
PENDING=$(echo "$PENDING" | tr -d ' ')
if [ "$PENDING" -gt 0 ]; then
  echo "" >> "$MEMORY_FILE"
  echo "## Pending Session Extractions" >> "$MEMORY_FILE"
  echo "$PENDING session note(s) have \`deep-extract: pending\` in Sessions/. Dispatch a background agent to run deep extraction on these — read each skeleton note, find the matching session JSONL in ~/.claude/projects/, extract decisions/learnings/ideas/personal traits, fill in the skeleton sections, update project hubs, then change \`deep-extract: pending\` to \`deep-extract: done\`." >> "$MEMORY_FILE"
fi

exit 0
