#!/usr/bin/env bash
set -euo pipefail

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo -e "${BLUE}"
echo "  ____      _         _ _ "
echo " |  _ \ ___| | ____ _| | |"
echo " | |_) / _ \ |/ / _\` | | |"
echo " |  _ <  __/   < (_| | | |"
echo " |_| \_\___|_|\_\__,_|_|_|"
echo ""
echo " A second brain that builds itself."
echo -e "${NC}"

# Step 1: Get user name
echo -e "${GREEN}What's your name?${NC}"
read -r USER_NAME
if [ -z "$USER_NAME" ]; then
  echo "Name is required."
  exit 1
fi

# Step 2: Get vault path
DEFAULT_VAULT="$HOME/Documents/Obsidian Vault"
echo -e "${GREEN}Where should your vault live?${NC} (default: $DEFAULT_VAULT)"
read -r VAULT_PATH
VAULT_PATH="${VAULT_PATH:-$DEFAULT_VAULT}"

# Expand ~ if present
VAULT_PATH="${VAULT_PATH/#\~/$HOME}"

echo ""
echo -e "${BLUE}Setting up Rekall for ${USER_NAME} at ${VAULT_PATH}${NC}"
echo ""

# Step 3: Create vault from template
echo -e "${YELLOW}[1/7] Creating vault...${NC}"
for dir in Projects Research Decisions Ideas Sessions; do
  mkdir -p "$VAULT_PATH/$dir"
done

# Copy template files (don't overwrite existing)
for file in Home.md AGENDA.md; do
  if [ ! -f "$VAULT_PATH/$file" ]; then
    sed "s/{{DATE}}/$(date +%Y-%m-%d)/g" "$SCRIPT_DIR/vault/$file" > "$VAULT_PATH/$file"
  fi
done

# Create About file
ABOUT_FILE="$VAULT_PATH/About ${USER_NAME}.md"
if [ ! -f "$ABOUT_FILE" ]; then
  cat > "$ABOUT_FILE" << EOF
---
date: $(date +%Y-%m-%d)
tags: [reference]
status: active
summary: "Profile and preferences for ${USER_NAME}"
---

# About ${USER_NAME}

## Role & Background
_What do you do? What's your expertise?_

## Preferences
_How do you like to work? What matters to you?_

## Working Style
_Communication preferences, tools, habits._
EOF
fi

# Step 4: Copy hooks
echo -e "${YELLOW}[2/7] Installing hooks...${NC}"
mkdir -p "$HOME/.claude/hooks"
for hook in session-logger.py compile-memory.sh vault-lint.sh secrets-check.sh dangerous-cmd-check.sh file-size-check.sh; do
  cp "$SCRIPT_DIR/hooks/$hook" "$HOME/.claude/hooks/$hook"
done
chmod +x "$HOME/.claude/hooks/"*.sh

# Set vault path in hooks
sed -i "s|{{VAULT_PATH}}|$VAULT_PATH|g" "$HOME/.claude/hooks/session-logger.py"
sed -i "s|{{VAULT_PATH}}|$VAULT_PATH|g" "$HOME/.claude/hooks/compile-memory.sh"
sed -i "s|{{VAULT_PATH}}|$VAULT_PATH|g" "$HOME/.claude/hooks/vault-lint.sh"

# Step 5: Copy commands
echo -e "${YELLOW}[3/7] Installing commands...${NC}"
mkdir -p "$HOME/.claude/commands"
for cmd in "$SCRIPT_DIR/commands/"*.md; do
  cp "$cmd" "$HOME/.claude/commands/"
done

# Step 6: Set up memory
echo -e "${YELLOW}[4/7] Setting up memory system...${NC}"
# Find or create project memory directory
CWD_ENCODED=$(pwd | sed 's/[^a-zA-Z0-9]/-/g')
MEMORY_DIR="$HOME/.claude/projects/$CWD_ENCODED/memory"
mkdir -p "$MEMORY_DIR"
if [ ! -f "$MEMORY_DIR/instincts.jsonl" ]; then
  cp "$SCRIPT_DIR/memory/instincts.jsonl" "$MEMORY_DIR/"
fi
if [ ! -f "$MEMORY_DIR/MEMORY.md" ]; then
  cp "$SCRIPT_DIR/memory/MEMORY.md" "$MEMORY_DIR/"
fi

# Step 7: Patch CLAUDE.md
echo -e "${YELLOW}[5/7] Configuring CLAUDE.md...${NC}"
CLAUDE_MD="$HOME/.claude/CLAUDE.md"
REKALL_SECTION="$SCRIPT_DIR/CLAUDE.md"

# Replace placeholders
PATCHED=$(sed "s|{{VAULT_PATH}}|$VAULT_PATH|g; s|{{USER_NAME}}|$USER_NAME|g; s|{{MEMORY_DIR}}|$MEMORY_DIR|g; s|{{DATE}}|$(date +%Y-%m-%d)|g" "$REKALL_SECTION")

if [ -f "$CLAUDE_MD" ]; then
  # Check if Rekall section already exists
  if grep -q "Rekall" "$CLAUDE_MD"; then
    echo "  CLAUDE.md already has Rekall config — skipping (delete the Rekall section to regenerate)"
  else
    echo "" >> "$CLAUDE_MD"
    echo "$PATCHED" >> "$CLAUDE_MD"
  fi
else
  echo "$PATCHED" > "$CLAUDE_MD"
fi

# Step 8: Merge settings.json
echo -e "${YELLOW}[6/7] Configuring settings.json...${NC}"
SETTINGS="$HOME/.claude/settings.json"

python3 << PYEOF
import json
import os

settings_path = os.path.expanduser("~/.claude/settings.json")
vault_path = "$VAULT_PATH"

# Load existing or create new
if os.path.exists(settings_path):
    with open(settings_path) as f:
        settings = json.load(f)
else:
    settings = {}

# Ensure permissions.allow exists
settings.setdefault("permissions", {}).setdefault("allow", [])

# Add vault permissions (if not already present)
vault_perms = [
    f"Read({vault_path}/**)",
    f"Edit({vault_path}/**)",
    f"Write({vault_path}/**)",
    f"Glob({vault_path}/**)",
    f"Grep({vault_path}/**)",
]
for perm in vault_perms:
    # Normalize backslashes for comparison
    normalized = perm.replace("/", os.sep)
    existing_normalized = [p.replace("/", os.sep) for p in settings["permissions"]["allow"]]
    if normalized not in existing_normalized and perm not in settings["permissions"]["allow"]:
        settings["permissions"]["allow"].append(perm)

# Ensure hooks exist
settings.setdefault("hooks", {})

# Add PreToolUse hooks
settings["hooks"].setdefault("PreToolUse", [])
pre_hooks = {
    "Write|Edit": "bash \"\$HOME/.claude/hooks/secrets-check.sh\"",
    "Bash": "bash \"\$HOME/.claude/hooks/dangerous-cmd-check.sh\"",
}
for matcher, cmd in pre_hooks.items():
    exists = any(
        h.get("matcher") == matcher and
        any(hh.get("command") == cmd for hh in h.get("hooks", []))
        for h in settings["hooks"]["PreToolUse"]
    )
    if not exists:
        settings["hooks"]["PreToolUse"].append({
            "matcher": matcher,
            "hooks": [{"type": "command", "command": cmd, "timeout": 10}]
        })

# Add PostToolUse hooks
settings["hooks"].setdefault("PostToolUse", [])
post_hooks = [
    ("Write|Edit", "bash \"\$HOME/.claude/hooks/file-size-check.sh\""),
    ("Write|Edit", "bash \"\$HOME/.claude/hooks/vault-lint.sh\""),
]
for matcher, cmd in post_hooks:
    exists = any(
        h.get("matcher") == matcher and
        any(hh.get("command") == cmd for hh in h.get("hooks", []))
        for h in settings["hooks"]["PostToolUse"]
    )
    if not exists:
        settings["hooks"]["PostToolUse"].append({
            "matcher": matcher,
            "hooks": [{"type": "command", "command": cmd, "timeout": 10}]
        })

# Add SessionStart hook
settings["hooks"].setdefault("SessionStart", [])
session_cmd = "bash \"\$HOME/.claude/hooks/compile-memory.sh\""
exists = any(
    any(hh.get("command") == session_cmd for hh in h.get("hooks", []))
    for h in settings["hooks"]["SessionStart"]
)
if not exists:
    settings["hooks"]["SessionStart"].append({
        "matcher": "startup|resume",
        "hooks": [{"type": "command", "command": session_cmd, "timeout": 15}]
    })

with open(settings_path, "w") as f:
    json.dump(settings, f, indent=2)

print("  Settings merged successfully")
PYEOF

# Step 9: Configure MCP
echo -e "${YELLOW}[7/7] Configuring MCP server...${NC}"
MCP_JSON="$HOME/.claude/mcp.json"

python3 << PYEOF
import json
import os

mcp_path = os.path.expanduser("~/.claude/mcp.json")
vault_path = "$VAULT_PATH"

if os.path.exists(mcp_path):
    with open(mcp_path) as f:
        mcp = json.load(f)
else:
    mcp = {}

mcp.setdefault("mcpServers", {})

if "obsidian" not in mcp["mcpServers"]:
    mcp["mcpServers"]["obsidian"] = {
        "command": "npx",
        "args": ["-y", "@bitbonsai/mcpvault@latest", vault_path]
    }
    print("  MCP obsidian server configured")
else:
    print("  MCP obsidian server already configured — skipping")

with open(mcp_path, "w") as f:
    json.dump(mcp, f, indent=2)
PYEOF

# Copy project mappings example
if [ ! -f "$HOME/.claude/rekall-projects.json" ]; then
  cp "$SCRIPT_DIR/rekall-projects.json.example" "$HOME/.claude/rekall-projects.json"
fi

echo ""
echo -e "${GREEN}✓ Rekall installed!${NC}"
echo ""
echo "  Vault:    $VAULT_PATH"
echo "  About:    About ${USER_NAME}.md"
echo "  Hooks:    ~/.claude/hooks/ (6 hooks)"
echo "  Commands: ~/.claude/commands/ (4 commands)"
echo "  Memory:   $MEMORY_DIR"
echo ""
echo -e "${BLUE}Start a new Claude Code session — your past conversations will be processed automatically.${NC}"
echo ""
echo "  Commands available:"
echo "    /session-log          — capture current session"
echo "    /vault-health         — audit vault health"
echo "    /vault-consolidate    — synthesize project knowledge"
echo "    /instincts-review     — review memory system"
