#!/usr/bin/env bash
# file-size-check.sh — PostToolUse hook for Write|Edit
# Warns (non-blocking) when a file exceeds 400 lines.

set -euo pipefail

# --- Load config ---
CONFIG_FILE="$HOME/.claude/rekall.conf"
if [ -f "$CONFIG_FILE" ]; then
  # shellcheck source=/dev/null
  source "$CONFIG_FILE"
fi

PYTHON="${REKALL_PYTHON:-}"

# Resolve Python if not set by config
if [ -z "$PYTHON" ]; then
  for cmd in python3 python; do
    if command -v "$cmd" > /dev/null 2>&1; then
      PYTHON="$cmd"
      break
    fi
  done
fi

if [ -z "$PYTHON" ]; then
  exit 0
fi

INPUT=$(cat)
FILE_PATH=$(printf '%s' "$INPUT" | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))" 2>/dev/null)

if [ -z "$FILE_PATH" ] || [ ! -f "$FILE_PATH" ]; then
  exit 0
fi

# Skip non-code files
case "$FILE_PATH" in
  *.md|*.txt|*.json|*.jsonl|*.csv|*.svg|*.lock|*.yaml|*.yml) exit 0 ;;
esac

LINE_COUNT=$(wc -l < "$FILE_PATH" 2>/dev/null || printf '0')
LINE_COUNT=$(printf '%s' "$LINE_COUNT" | tr -d ' ')

if [ "$LINE_COUNT" -gt 400 ]; then
  printf "WARNING: %s is %s lines (threshold: 400). Consider splitting into smaller modules.\n" "$FILE_PATH" "$LINE_COUNT" >&2
fi

exit 0
