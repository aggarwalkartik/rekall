#!/usr/bin/env bash
# dangerous-cmd-check.sh — PreToolUse hook for Bash
# Blocks destructive shell commands before execution.

set -euo pipefail

# --- Extract command from stdin JSON without Python ---
INPUT=$(cat)
COMMAND=""
if [[ "$INPUT" =~ \"command\"[[:space:]]*:[[:space:]]*\"(([^\"\\]|\\.)*)\" ]]; then
  COMMAND="${BASH_REMATCH[1]}"
fi

if [ -z "$COMMAND" ]; then
  exit 0
fi

# Check each dangerous pattern
check_pattern() {
  local pattern="$1"
  local reason="$2"
  if printf '%s' "$COMMAND" | grep -qi "$pattern" 2>/dev/null; then
    printf "BLOCKED: Dangerous command detected — %s\n" "$reason" >&2
    printf "Command: %s\n" "$COMMAND" >&2
    printf "If you need this, ask the user for explicit confirmation first.\n" >&2
    exit 2
  fi
}

check_pattern "rm -rf /" "recursive delete from root"
check_pattern "rm -rf ~" "recursive delete home directory"
check_pattern 'rm -rf \.' "recursive delete current directory"
check_pattern 'rm -rf \*' "recursive delete everything"
check_pattern "git push --force" "force push (use --force-with-lease instead)"
check_pattern "git push -f " "force push (use --force-with-lease instead)"
check_pattern "git reset --hard" "hard reset discards all uncommitted changes"
check_pattern "git clean -fd" "removes untracked files and directories permanently"
check_pattern "git clean -f$" "removes untracked files permanently"
check_pattern "git clean -fx" "removes untracked and ignored files permanently"
check_pattern "DROP TABLE" "dropping database table"
check_pattern "DROP DATABASE" "dropping entire database"
check_pattern "TRUNCATE TABLE" "truncating database table"
check_pattern ':(){ :|:& };:' "fork bomb"
check_pattern 'mkfs\.' "formatting filesystem"
check_pattern "dd if=" "raw disk write"
check_pattern "> /dev/sda" "writing directly to disk"

exit 0
