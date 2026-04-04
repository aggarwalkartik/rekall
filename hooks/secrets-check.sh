#!/usr/bin/env bash
# secrets-check.sh — PreToolUse hook for Write|Edit
# Blocks file writes that contain secrets/credentials patterns.

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
      if "$cmd" -c 'import sys; sys.exit(0 if sys.version_info[0] >= 3 else 1)' 2>/dev/null; then
        PYTHON="$cmd"
        break
      fi
    fi
  done
fi

if [ -z "$PYTHON" ]; then
  exit 0
fi

# Single Python invocation: parse JSON from stdin, extract fields, check patterns.
# Avoids multiple process spawns and environment variable size limits.
"$PYTHON" << 'PYEOF' >&2
import json
import re
import sys

raw = sys.stdin.read()
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    sys.exit(0)

tool_name = data.get("tool_name", "")
tool_input = data.get("tool_input", {})

if tool_name == "Write":
    content = tool_input.get("content", "")
elif tool_name == "Edit":
    content = tool_input.get("new_string", "")
else:
    sys.exit(0)

if not content:
    sys.exit(0)

file_path = tool_input.get("file_path", "")

# Allowlist: skip memory files, markdown, examples, templates
for suffix in (".md", ".example", ".template"):
    if file_path.endswith(suffix):
        sys.exit(0)
for skip in ("memory", "CLAUDE"):
    if skip in file_path:
        sys.exit(0)

patterns = [
    (r'API_KEY\s*=\s*["\x27][A-Za-z0-9_\-]{16,}', "API_KEY assignment"),
    (r'SECRET_KEY\s*=\s*["\x27][A-Za-z0-9_\-]{16,}', "SECRET_KEY assignment"),
    (r'API_SECRET\s*=\s*["\x27][A-Za-z0-9_\-]{16,}', "API_SECRET assignment"),
    (r'PASSWORD\s*=\s*["\x27][^\s"\x27]{8,}', "PASSWORD assignment"),
    (r'PRIVATE_KEY\s*=\s*["\x27]', "PRIVATE_KEY assignment"),
    (r'Bearer\s+[A-Za-z0-9_\-\.]{20,}', "Bearer token"),
    (r'AKIA[0-9A-Z]{16}', "AWS access key"),
    (r'ghp_[A-Za-z0-9]{36}', "GitHub personal access token"),
    (r'sk-[A-Za-z0-9]{32,}', "OpenAI/Stripe secret key"),
    (r'xox[bpoas]-[A-Za-z0-9\-]{10,}', "Slack token"),
]

for pattern, label in patterns:
    match = re.search(pattern, content)
    if match:
        preview = match.group(0)[:20]
        print(f"BLOCKED: Potential secret detected — {label}")
        print(f"Match preview: {preview}...")
        print(f"File: {file_path}")
        print("If this is intentional, use a .example or .template extension.")
        sys.exit(2)

sys.exit(0)
PYEOF
# Python exits 2 if secret found (blocks the tool), 0 if clean.
# With set -e, a non-zero exit propagates automatically.
