#!/usr/bin/env bash
# vault-researcher.sh — PreToolUse hook for WebSearch
# Searches the Obsidian vault before every web search and injects
# matching notes as additionalContext. WebSearch always proceeds.

set -euo pipefail

# --- Load config ---
CONFIG_FILE="$HOME/.claude/rekall.conf"
if [ -f "$CONFIG_FILE" ]; then
  # shellcheck source=/dev/null
  source "$CONFIG_FILE"
fi

VAULT_PATH="${REKALL_VAULT_PATH:-$HOME/Obsidian Vault}"

# Exit silently if vault doesn't exist
if [ ! -d "$VAULT_PATH" ]; then
  exit 0
fi

# --- Read tool input from stdin ---
INPUT=$(cat)

# Extract the search query from JSON
QUERY=""
if [[ "$INPUT" =~ \"query\"[[:space:]]*:[[:space:]]*\"([^\"]+)\" ]]; then
  QUERY="${BASH_REMATCH[1]}"
fi

if [ -z "$QUERY" ]; then
  exit 0
fi

# --- Strip stopwords and extract keywords ---
STOPWORDS="a an the is are was were what how why when where which who do does did can could should would about for with from into on at to in of and or but not best latest recent current new top"

KEYWORDS=""
for WORD in $QUERY; do
  LOWER=$(printf '%s' "$WORD" | tr '[:upper:]' '[:lower:]' | tr -cd '[:alnum:]')
  if [ -z "$LOWER" ] || [ ${#LOWER} -lt 3 ]; then
    continue
  fi
  SKIP=0
  for SW in $STOPWORDS; do
    if [ "$LOWER" = "$SW" ]; then
      SKIP=1
      break
    fi
  done
  if [ "$SKIP" -eq 0 ]; then
    KEYWORDS="${KEYWORDS} ${LOWER}"
  fi
done

KEYWORDS=$(printf '%s' "$KEYWORDS" | xargs)

if [ -z "$KEYWORDS" ]; then
  exit 0
fi

# --- Search vault ---
MATCHES=""
MATCH_COUNT=0
MAX_MATCHES=5

# Search filenames first (highest signal)
for DIR in "Research" "Decisions"; do
  if [ ! -d "$VAULT_PATH/$DIR" ]; then
    continue
  fi
  for KEYWORD in $KEYWORDS; do
    if [ "$MATCH_COUNT" -ge "$MAX_MATCHES" ]; then
      break 2
    fi
    # Case-insensitive filename search
    while IFS= read -r FILE; do
      if [ -z "$FILE" ]; then continue; fi
      BASENAME=$(basename "$FILE" .md)
      # Skip if already matched
      if printf '%s' "$MATCHES" | grep -qF "$BASENAME"; then
        continue
      fi
      # Extract frontmatter summary and tags (first 10 lines)
      SUMMARY=""
      TAGS=""
      HEAD=$(head -10 "$FILE" 2>/dev/null || true)
      if [ -n "$HEAD" ]; then
        SUMMARY=$(printf '%s' "$HEAD" | grep "^summary:" | sed 's/summary: *"//;s/"$//' | head -1)
        TAGS=$(printf '%s' "$HEAD" | grep "^tags:" | sed 's/tags: *//' | head -1)
      fi
      MATCHES="${MATCHES}- ${DIR}/${BASENAME}.md"
      if [ -n "$TAGS" ]; then
        MATCHES="${MATCHES} (tags: ${TAGS})"
      fi
      if [ -n "$SUMMARY" ]; then
        MATCHES="${MATCHES} — ${SUMMARY}"
      fi
      MATCHES="${MATCHES}\n"
      MATCH_COUNT=$((MATCH_COUNT + 1))
      if [ "$MATCH_COUNT" -ge "$MAX_MATCHES" ]; then
        break
      fi
    done < <(find "$VAULT_PATH/$DIR" -maxdepth 1 -iname "*${KEYWORD}*" -name "*.md" 2>/dev/null)
  done
done

# If fewer than MAX_MATCHES, search frontmatter content
if [ "$MATCH_COUNT" -lt "$MAX_MATCHES" ]; then
  for DIR in "Research" "Decisions"; do
    if [ ! -d "$VAULT_PATH/$DIR" ]; then
      continue
    fi
    for KEYWORD in $KEYWORDS; do
      if [ "$MATCH_COUNT" -ge "$MAX_MATCHES" ]; then
        break 2
      fi
      # Search summary and tags lines in frontmatter
      while IFS= read -r FILE; do
        if [ -z "$FILE" ]; then continue; fi
        BASENAME=$(basename "$FILE" .md)
        if printf '%s' "$MATCHES" | grep -qF "$BASENAME"; then
          continue
        fi
        SUMMARY=""
        TAGS=""
        HEAD=$(head -10 "$FILE" 2>/dev/null || true)
        if [ -n "$HEAD" ]; then
          SUMMARY=$(printf '%s' "$HEAD" | grep "^summary:" | sed 's/summary: *"//;s/"$//' | head -1)
          TAGS=$(printf '%s' "$HEAD" | grep "^tags:" | sed 's/tags: *//' | head -1)
        fi
        MATCHES="${MATCHES}- ${DIR}/${BASENAME}.md"
        if [ -n "$TAGS" ]; then
          MATCHES="${MATCHES} (tags: ${TAGS})"
        fi
        if [ -n "$SUMMARY" ]; then
          MATCHES="${MATCHES} — ${SUMMARY}"
        fi
        MATCHES="${MATCHES}\n"
        MATCH_COUNT=$((MATCH_COUNT + 1))
        if [ "$MATCH_COUNT" -ge "$MAX_MATCHES" ]; then
          break
        fi
      done < <(grep -rli "$KEYWORD" "$VAULT_PATH/$DIR"/*.md 2>/dev/null | head -5)
    done
  done
fi

# --- Output ---
if [ "$MATCH_COUNT" -eq 0 ]; then
  exit 0
fi

CONTEXT="VAULT CHECK: Found existing notes that may be relevant to this search:\n${MATCHES}\nConsider reading these before interpreting web results. If web results add new findings to an existing note, append an '## Updated Findings ($(date +%Y-%m-%d))' section with source URLs rather than creating a duplicate note."

# Output JSON for additionalContext injection
printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","additionalContext":"%s"}}' "$(printf '%b' "$CONTEXT" | sed 's/"/\\"/g' | tr '\n' ' ')"

exit 0
