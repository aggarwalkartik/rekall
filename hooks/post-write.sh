#!/usr/bin/env bash
# post-write.sh — PostToolUse hook for Write|Edit
# Combines vault linting and file size checking in a single hook.
# One process spawn instead of two.

set -euo pipefail

# --- Load config ---
CONFIG_FILE="$HOME/.claude/rekall.conf"
if [ -f "$CONFIG_FILE" ]; then
  # shellcheck source=/dev/null
  source "$CONFIG_FILE"
fi

VAULT_PATH="${REKALL_VAULT_PATH:-$HOME/Obsidian Vault}"

# --- Extract file_path from stdin JSON without Python ---
# Claude Code hook input is a single JSON object. We extract file_path
# using bash string manipulation on the predictable JSON structure.
INPUT=$(cat)
# Match "file_path": "..." — handles paths with spaces and special chars
FILE_PATH=""
if [[ "$INPUT" =~ \"file_path\"[[:space:]]*:[[:space:]]*\"([^\"]+)\" ]]; then
  FILE_PATH="${BASH_REMATCH[1]}"
fi

if [ -z "$FILE_PATH" ]; then
  exit 0
fi

# ============================================================
# CHECK 1: File size (non-blocking warning)
# ============================================================
if [ -f "$FILE_PATH" ]; then
  case "$FILE_PATH" in
    *.md|*.txt|*.json|*.jsonl|*.csv|*.svg|*.lock|*.yaml|*.yml) ;;
    *)
      LINE_COUNT=$(wc -l < "$FILE_PATH" 2>/dev/null || printf '0')
      LINE_COUNT=$(printf '%s' "$LINE_COUNT" | tr -d ' ')
      if [ "$LINE_COUNT" -gt 400 ]; then
        printf "WARNING: %s is %s lines (threshold: 400). Consider splitting into smaller modules.\n" "$FILE_PATH" "$LINE_COUNT" >&2
      fi
      ;;
  esac
fi

# ============================================================
# CHECK 2: Vault lint (non-blocking warnings)
# ============================================================

# Only lint files inside the vault (exact prefix match)
case "$FILE_PATH" in
  "$VAULT_PATH"/*) ;;
  *) exit 0 ;;
esac

# Only lint markdown files
case "$FILE_PATH" in
  *.md) ;;
  *) exit 0 ;;
esac

# Skip root-level special files
BASENAME=$(basename "$FILE_PATH")
case "$BASENAME" in
  Home.md|About*.md|AGENDA.md) exit 0 ;;
esac

if [ ! -f "$FILE_PATH" ]; then
  exit 0
fi

CONTENT=$(cat "$FILE_PATH")
WARNINGS=""

# Check: Frontmatter exists and has required fields
if ! printf '%s' "$CONTENT" | head -1 | grep -q "^---$"; then
  WARNINGS="${WARNINGS}  - Missing YAML frontmatter\n"
else
  FRONTMATTER=$(printf '%s' "$CONTENT" | sed -n '/^---$/,/^---$/p')
  for FIELD in "date:" "tags:" "status:" "summary:"; do
    if ! printf '%s' "$FRONTMATTER" | grep -q "$FIELD"; then
      WARNINGS="${WARNINGS}  - Missing frontmatter field: ${FIELD%:}\n"
    fi
  done

  # Check allowed status values
  STATUS=$(printf '%s' "$FRONTMATTER" | grep "^status:" | sed 's/status: *//')
  case "$STATUS" in
    active|stale|archived|"") ;;
    *) WARNINGS="${WARNINGS}  - Invalid status '$STATUS' (must be: active, stale, archived)\n" ;;
  esac

  # Check allowed tags
  TAGS_LINE=$(printf '%s' "$FRONTMATTER" | grep "^tags:" || true)
  if [ -n "$TAGS_LINE" ]; then
    ALLOWED_TYPE="project research reference decision idea session"
    ALLOWED_DOMAIN="design business finance dev personal knowledge-management data-viz email job-search"
    ALL_ALLOWED="$ALLOWED_TYPE $ALLOWED_DOMAIN"

    TAGS=$(printf '%s' "$TAGS_LINE" | sed 's/tags: *\[//;s/\]//;s/,/ /g;s/"//g;s/'"'"'//g')
    for TAG in $TAGS; do
      TAG=$(printf '%s' "$TAG" | xargs)
      if [ -z "$TAG" ]; then continue; fi
      FOUND=0
      for A in $ALL_ALLOWED; do
        if [ "$TAG" = "$A" ]; then FOUND=1; break; fi
      done
      if [ "$FOUND" -eq 0 ]; then
        WARNINGS="${WARNINGS}  - Tag '$TAG' is not in the allowed list\n"
      fi
    done
  fi
fi

# Check: Note has at least one wikilink
if ! printf '%s' "$CONTENT" | grep -q "\[\["; then
  WARNINGS="${WARNINGS}  - No wikilinks found (every note needs at least one [[link]])\n"
fi

# Check: Research/Decision notes need Parent: link
case "$FILE_PATH" in
  *Research/*|*Decisions/*)
    if ! printf '%s' "$CONTENT" | grep -q "^Parent:"; then
      WARNINGS="${WARNINGS}  - Research/Decision note missing 'Parent: [[Project Hub]]' line\n"
    fi
    ;;
esac

# Check: Filename should be Title Case with spaces (no kebab-case)
if printf '%s' "$BASENAME" | perl -ne 'exit 0 if /^[a-z]+-[a-z]/; exit 1' 2>/dev/null; then
  WARNINGS="${WARNINGS}  - Filename appears to be kebab-case: $BASENAME (use Title Case With Spaces)\n"
fi

# Output warnings if any
if [ -n "$WARNINGS" ]; then
  printf "VAULT LINT — %s:\n" "$BASENAME" >&2
  printf '%b' "$WARNINGS" >&2
fi

exit 0
