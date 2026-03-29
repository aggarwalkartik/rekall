#!/usr/bin/env bash
# secrets-check.sh — PreToolUse hook for Write|Edit
# Blocks file writes that contain secrets/credentials patterns.

set -euo pipefail

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | python -c "import sys,json; print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null)

if [ "$TOOL_NAME" = "Write" ]; then
  CONTENT=$(echo "$INPUT" | python -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('content',''))" 2>/dev/null)
elif [ "$TOOL_NAME" = "Edit" ]; then
  CONTENT=$(echo "$INPUT" | python -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('new_string',''))" 2>/dev/null)
else
  exit 0
fi

if [ -z "$CONTENT" ]; then
  exit 0
fi

FILE_PATH=$(echo "$INPUT" | python -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))" 2>/dev/null)

# Allowlist: skip memory files, markdown, examples, templates
case "$FILE_PATH" in
  *.md) exit 0 ;;
  *memory*) exit 0 ;;
  *CLAUDE*) exit 0 ;;
  *.example*) exit 0 ;;
  *.template*) exit 0 ;;
esac

# Secret patterns to check
PATTERNS=(
  'API_KEY\s*=\s*["\x27][A-Za-z0-9_\-]{16,}'
  'SECRET_KEY\s*=\s*["\x27][A-Za-z0-9_\-]{16,}'
  'API_SECRET\s*=\s*["\x27][A-Za-z0-9_\-]{16,}'
  'PASSWORD\s*=\s*["\x27][^\s"'\'']{8,}'
  'PRIVATE_KEY\s*=\s*["\x27]'
  'Bearer\s+[A-Za-z0-9_\-\.]{20,}'
  'AKIA[0-9A-Z]{16}'
  'ghp_[A-Za-z0-9]{36}'
  'sk-[A-Za-z0-9]{32,}'
  'xox[bpoas]-[A-Za-z0-9\-]{10,}'
)

for PATTERN in "${PATTERNS[@]}"; do
  if echo "$CONTENT" | grep -qP "$PATTERN" 2>/dev/null; then
    MATCH=$(echo "$CONTENT" | grep -oP "$PATTERN" 2>/dev/null | head -1)
    echo "BLOCKED: Potential secret detected matching pattern: ${PATTERN}" >&2
    echo "Match preview: ${MATCH:0:20}..." >&2
    echo "File: $FILE_PATH" >&2
    echo "If this is intentional, use a .example or .template extension." >&2
    exit 2
  fi
done

exit 0
