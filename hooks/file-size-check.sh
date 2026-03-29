#!/usr/bin/env bash
# file-size-check.sh — PostToolUse hook for Write|Edit
# Warns (non-blocking) when a file exceeds 400 lines.

set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | python -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))" 2>/dev/null)

if [ -z "$FILE_PATH" ] || [ ! -f "$FILE_PATH" ]; then
  exit 0
fi

# Skip non-code files
case "$FILE_PATH" in
  *.md|*.txt|*.json|*.jsonl|*.csv|*.svg|*.lock|*.yaml|*.yml) exit 0 ;;
esac

LINE_COUNT=$(wc -l < "$FILE_PATH" 2>/dev/null || echo "0")
LINE_COUNT=$(echo "$LINE_COUNT" | tr -d ' ')

if [ "$LINE_COUNT" -gt 400 ]; then
  echo "WARNING: $FILE_PATH is $LINE_COUNT lines (threshold: 400). Consider splitting into smaller modules." >&2
fi

exit 0
