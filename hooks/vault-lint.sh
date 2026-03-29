#!/usr/bin/env bash
# vault-lint.sh — PostToolUse hook for Write|Edit
# Warns (non-blocking) when vault notes violate conventions.

set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | python -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))" 2>/dev/null)

VAULT_PATH="${REKALL_VAULT_PATH:-$HOME/Documents/Obsidian Vault}"

# Only lint files in the Obsidian Vault
case "$FILE_PATH" in
  *"${VAULT_PATH##*/}"*) ;;
  *) exit 0 ;;
esac

# Skip non-markdown files
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

# Check 1: Frontmatter exists and has required fields
if ! echo "$CONTENT" | head -1 | grep -q "^---$"; then
  WARNINGS="${WARNINGS}  - Missing YAML frontmatter\n"
else
  FRONTMATTER=$(echo "$CONTENT" | sed -n '/^---$/,/^---$/p')
  for FIELD in "date:" "tags:" "status:" "summary:"; do
    if ! echo "$FRONTMATTER" | grep -q "$FIELD"; then
      WARNINGS="${WARNINGS}  - Missing frontmatter field: ${FIELD%:}\n"
    fi
  done

  # Check allowed status values
  STATUS=$(echo "$FRONTMATTER" | grep "^status:" | sed 's/status: *//')
  case "$STATUS" in
    active|stale|archived|"") ;;
    *) WARNINGS="${WARNINGS}  - Invalid status '$STATUS' (must be: active, stale, archived)\n" ;;
  esac

  # Check allowed tags
  TAGS_LINE=$(echo "$FRONTMATTER" | grep "^tags:" || true)
  if [ -n "$TAGS_LINE" ]; then
    ALLOWED_TYPE="project research reference decision idea session"
    ALLOWED_DOMAIN="design business finance dev personal knowledge-management data-viz email job-search"
    ALL_ALLOWED="$ALLOWED_TYPE $ALLOWED_DOMAIN"

    # Extract tags from YAML array
    TAGS=$(echo "$TAGS_LINE" | sed 's/tags: *\[//;s/\]//;s/,/ /g;s/"//g;s/'"'"'//g')
    for TAG in $TAGS; do
      TAG=$(echo "$TAG" | xargs)
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

# Check 2: Note has at least one wikilink
if ! echo "$CONTENT" | grep -q "\[\["; then
  WARNINGS="${WARNINGS}  - No wikilinks found (every note needs at least one [[link]])\n"
fi

# Check 3: Research/Decision notes need Parent: link
case "$FILE_PATH" in
  *Research/*|*Decisions/*)
    if ! echo "$CONTENT" | grep -q "^Parent:"; then
      WARNINGS="${WARNINGS}  - Research/Decision note missing 'Parent: [[Project Hub]]' line\n"
    fi
    ;;
esac

# Check 4: Filename should be Title Case with spaces (no kebab-case)
if echo "$BASENAME" | grep -qP "^[a-z]+-[a-z]" 2>/dev/null; then
  WARNINGS="${WARNINGS}  - Filename appears to be kebab-case: $BASENAME (use Title Case With Spaces)\n"
fi

# Output warnings if any
if [ -n "$WARNINGS" ]; then
  echo "VAULT LINT — $BASENAME:" >&2
  echo -e "$WARNINGS" >&2
fi

exit 0
