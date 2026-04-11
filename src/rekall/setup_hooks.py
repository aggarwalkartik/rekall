"""Post-install setup for Claude Code integration."""
from __future__ import annotations
import json
import shutil
import sys
from pathlib import Path

CLAUDE_MD_SNIPPET = """
## Rekall — Personal Knowledge Base

Before researching any topic, call the Rekall `recall` tool to check if you already have knowledge on it. Use `remember` to save decisions, preferences, and important facts during conversations.
"""

HOOK_CONFIG = {
    "type": "command",
    "command": "rekall-extract --background && rekall-compile",
    "timeout": 30,
}


def setup_claude_code() -> None:
    """Add Rekall hooks and CLAUDE.md snippet for Claude Code."""
    claude_dir = Path.home() / ".claude"

    # --- Add MCP server config ---
    mcp_path = claude_dir / "mcp.json"
    mcp_config = {}
    if mcp_path.exists():
        mcp_config = json.loads(mcp_path.read_text())
    mcp_config.setdefault("mcpServers", {})
    # Use local path until published to PyPI under a unique name
    # (the "rekall" name on PyPI is taken by a memory forensics tool)
    rekall_dir = str(Path(__file__).resolve().parent.parent.parent)
    mcp_config["mcpServers"]["rekall"] = {
        "command": "uv",
        "args": ["run", "--directory", rekall_dir, "rekall"],
    }
    mcp_path.write_text(json.dumps(mcp_config, indent=2))
    print(f"Updated {mcp_path}", file=sys.stderr)

    # --- Add SessionStart hook ---
    settings_path = claude_dir / "settings.json"
    settings = {}
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())
    settings.setdefault("hooks", {})
    settings["hooks"].setdefault("SessionStart", [])

    # Remove any existing Rekall hooks
    existing = settings["hooks"]["SessionStart"]
    settings["hooks"]["SessionStart"] = [
        h for h in existing
        if not any(
            "rekall" in hook.get("command", "").lower()
            or "compile-memory" in hook.get("command", "").lower()
            or "session-logger" in hook.get("command", "").lower()
            for hook in h.get("hooks", [])
        )
    ]

    # Add new hook
    settings["hooks"]["SessionStart"].append({
        "matcher": "",
        "hooks": [HOOK_CONFIG],
    })
    settings_path.write_text(json.dumps(settings, indent=2))
    print(f"Updated {settings_path}", file=sys.stderr)

    # --- Add CLAUDE.md snippet ---
    claude_md = claude_dir / "CLAUDE.md"
    if claude_md.exists():
        content = claude_md.read_text()
        if "Rekall" not in content:
            content += "\n" + CLAUDE_MD_SNIPPET
            claude_md.write_text(content)
            print(f"Added Rekall snippet to {claude_md}", file=sys.stderr)
        else:
            print(f"Rekall snippet already in {claude_md}", file=sys.stderr)
    else:
        claude_md.write_text(CLAUDE_MD_SNIPPET.strip())
        print(f"Created {claude_md}", file=sys.stderr)


    # --- Copy safety hooks ---
    hooks_src = Path(__file__).resolve().parent.parent.parent / "hooks"
    hooks_dst = claude_dir / "hooks"
    hooks_dst.mkdir(parents=True, exist_ok=True)

    for hook_name in ["secrets-check.sh", "dangerous-cmd-check.sh"]:
        src = hooks_src / hook_name
        dst = hooks_dst / hook_name
        if src.exists():
            shutil.copy2(src, dst)
            dst.chmod(0o755)
            print(f"Installed {dst}", file=sys.stderr)
        else:
            print(f"Warning: {src} not found, skipping", file=sys.stderr)

    # --- Add safety hook configs to settings ---
    # Re-read settings (we already wrote SessionStart above)
    settings = json.loads(settings_path.read_text())
    settings["hooks"].setdefault("PreToolUse", [])

    # Remove old Rekall PreToolUse hooks, keep non-Rekall ones
    existing_pre = settings["hooks"]["PreToolUse"]
    settings["hooks"]["PreToolUse"] = [
        h for h in existing_pre
        if not any(
            "secrets-check" in hook.get("command", "").lower()
            or "dangerous-cmd" in hook.get("command", "").lower()
            for hook in h.get("hooks", [])
        )
    ]

    # Add secrets check on Write/Edit
    settings["hooks"]["PreToolUse"].append({
        "matcher": "Write|Edit",
        "hooks": [{
            "type": "command",
            "command": f"bash {hooks_dst / 'secrets-check.sh'}",
            "timeout": 10,
        }],
    })

    # Add dangerous command check on Bash
    settings["hooks"]["PreToolUse"].append({
        "matcher": "Bash",
        "hooks": [{
            "type": "command",
            "command": f"bash {hooks_dst / 'dangerous-cmd-check.sh'}",
            "timeout": 10,
        }],
    })

    settings_path.write_text(json.dumps(settings, indent=2))
    print(f"Added safety hooks to {settings_path}", file=sys.stderr)


if __name__ == "__main__":
    setup_claude_code()
