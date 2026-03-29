#Requires -Version 5.1
<#
.SYNOPSIS
    Rekall setup script for Windows (PowerShell 5.1+).
    Port of setup.sh — same 7-step flow.
.DESCRIPTION
    Sets up Rekall: vault structure, hooks, commands, memory system,
    CLAUDE.md configuration, settings.json, and mcp.json.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------- ASCII art header ----------
Write-Host ""
Write-Host "  ____      _         _ _ " -ForegroundColor Blue
Write-Host " |  _ \ ___| | ____ _| | |" -ForegroundColor Blue
Write-Host " | |_) / _ \ |/ / _`` | | |" -ForegroundColor Blue
Write-Host " |  _ <  __/   < (_| | | |" -ForegroundColor Blue
Write-Host " |_| \_\___|_|\_\__,_|_|_|" -ForegroundColor Blue
Write-Host "" -ForegroundColor Blue
Write-Host " A second brain that builds itself." -ForegroundColor Blue
Write-Host ""

# ---------- Step 1: Get user name and vault path ----------
Write-Host "What's your name?" -ForegroundColor Green
$UserName = Read-Host
if ([string]::IsNullOrWhiteSpace($UserName)) {
    Write-Host "Name is required." -ForegroundColor Red
    exit 1
}

$DefaultVault = Join-Path $env:USERPROFILE "Documents\Obsidian Vault"
Write-Host "Where should your vault live? (default: $DefaultVault)" -ForegroundColor Green
$VaultPath = Read-Host
if ([string]::IsNullOrWhiteSpace($VaultPath)) {
    $VaultPath = $DefaultVault
}

# Expand ~ if present
if ($VaultPath.StartsWith("~")) {
    $VaultPath = $VaultPath -replace "^~", $env:USERPROFILE
}

Write-Host ""
Write-Host "Setting up Rekall for $UserName at $VaultPath" -ForegroundColor Blue
Write-Host ""

$Today = Get-Date -Format "yyyy-MM-dd"

# ---------- Step 2: Create vault from template ----------
Write-Host "[1/7] Creating vault..." -ForegroundColor Yellow
foreach ($dir in @("Projects", "Research", "Decisions", "Ideas", "Sessions")) {
    New-Item -ItemType Directory -Path (Join-Path $VaultPath $dir) -Force | Out-Null
}

# Copy template files (don't overwrite existing)
foreach ($file in @("Home.md", "AGENDA.md")) {
    $dest = Join-Path $VaultPath $file
    if (-not (Test-Path $dest)) {
        $content = Get-Content (Join-Path $PSScriptRoot "vault\$file") -Raw
        $content = $content -replace '\{\{DATE\}\}', $Today
        Set-Content -Path $dest -Value $content -NoNewline -Encoding UTF8
    }
}

# Create About file
$AboutFile = Join-Path $VaultPath "About ${UserName}.md"
if (-not (Test-Path $AboutFile)) {
    $aboutContent = @"
---
date: $Today
tags: [reference]
status: active
summary: "Profile and preferences for ${UserName}"
---

# About ${UserName}

## Role & Background
_What do you do? What's your expertise?_

## Preferences
_How do you like to work? What matters to you?_

## Working Style
_Communication preferences, tools, habits._
"@
    Set-Content -Path $AboutFile -Value $aboutContent -Encoding UTF8
}

# ---------- Step 3: Copy hooks ----------
Write-Host "[2/7] Installing hooks..." -ForegroundColor Yellow
$hooksDir = Join-Path $env:USERPROFILE ".claude\hooks"
New-Item -ItemType Directory -Path $hooksDir -Force | Out-Null

$hookFiles = @(
    "session-logger.py",
    "compile-memory.sh",
    "vault-lint.sh",
    "secrets-check.sh",
    "dangerous-cmd-check.sh",
    "file-size-check.sh"
)
foreach ($hook in $hookFiles) {
    Copy-Item (Join-Path $PSScriptRoot "hooks\$hook") (Join-Path $hooksDir $hook) -Force
}

# Set vault path in hooks that reference it
foreach ($hookToPath in @("session-logger.py", "compile-memory.sh", "vault-lint.sh")) {
    $hookFile = Join-Path $hooksDir $hookToPath
    $hookContent = Get-Content $hookFile -Raw
    $hookContent = $hookContent -replace '\{\{VAULT_PATH\}\}', ($VaultPath -replace '\\', '/')
    Set-Content -Path $hookFile -Value $hookContent -NoNewline -Encoding UTF8
}

# ---------- Step 4: Copy commands ----------
Write-Host "[3/7] Installing commands..." -ForegroundColor Yellow
$commandsDir = Join-Path $env:USERPROFILE ".claude\commands"
New-Item -ItemType Directory -Path $commandsDir -Force | Out-Null

$sourceCommands = Join-Path $PSScriptRoot "commands"
Get-ChildItem -Path $sourceCommands -Filter "*.md" | ForEach-Object {
    Copy-Item $_.FullName (Join-Path $commandsDir $_.Name) -Force
}

# ---------- Step 5: Set up memory ----------
Write-Host "[4/7] Setting up memory system..." -ForegroundColor Yellow

# Encode current working directory the same way as bash: replace non-alphanumeric with -
$cwdEncoded = (Get-Location).Path -replace '[^a-zA-Z0-9]', '-'
$MemoryDir = Join-Path $env:USERPROFILE ".claude\projects\$cwdEncoded\memory"
New-Item -ItemType Directory -Path $MemoryDir -Force | Out-Null

$instinctsFile = Join-Path $MemoryDir "instincts.jsonl"
if (-not (Test-Path $instinctsFile)) {
    Copy-Item (Join-Path $PSScriptRoot "memory\instincts.jsonl") $instinctsFile -Force
}

$memoryFile = Join-Path $MemoryDir "MEMORY.md"
if (-not (Test-Path $memoryFile)) {
    Copy-Item (Join-Path $PSScriptRoot "memory\MEMORY.md") $memoryFile -Force
}

# ---------- Step 6: Patch CLAUDE.md ----------
Write-Host "[5/7] Configuring CLAUDE.md..." -ForegroundColor Yellow
$claudeMd = Join-Path $env:USERPROFILE ".claude\CLAUDE.md"
$rekallSection = Join-Path $PSScriptRoot "CLAUDE.md"

# Read template and replace placeholders
# Use forward slashes for vault path (bash hooks expect it) and native for memory dir
$patched = Get-Content $rekallSection -Raw
$patched = $patched -replace '\{\{VAULT_PATH\}\}', ($VaultPath -replace '\\', '/')
$patched = $patched -replace '\{\{USER_NAME\}\}', $UserName
$patched = $patched -replace '\{\{MEMORY_DIR\}\}', ($MemoryDir -replace '\\', '/')
$patched = $patched -replace '\{\{DATE\}\}', $Today

if (Test-Path $claudeMd) {
    $existingContent = Get-Content $claudeMd -Raw
    if ($existingContent -match "Rekall") {
        Write-Host "  CLAUDE.md already has Rekall config - skipping (delete the Rekall section to regenerate)"
    } else {
        Add-Content -Path $claudeMd -Value "`n$patched" -Encoding UTF8
    }
} else {
    Set-Content -Path $claudeMd -Value $patched -Encoding UTF8
}

# ---------- Step 7a: Merge settings.json ----------
Write-Host "[6/7] Configuring settings.json..." -ForegroundColor Yellow
$settingsPath = Join-Path $env:USERPROFILE ".claude\settings.json"

# Use forward-slash vault path for settings (Claude Code uses forward slashes internally)
$vaultPathForward = $VaultPath -replace '\\', '/'

$settingsPy = @"
import json, os, sys

settings_path = r'$settingsPath'
vault_path = '$vaultPathForward'

if os.path.exists(settings_path):
    with open(settings_path, encoding='utf-8') as f:
        settings = json.load(f)
else:
    settings = {}

settings.setdefault('permissions', {}).setdefault('allow', [])

vault_perms = [
    f'Read({vault_path}/**)',
    f'Edit({vault_path}/**)',
    f'Write({vault_path}/**)',
    f'Glob({vault_path}/**)',
    f'Grep({vault_path}/**)',
]
for perm in vault_perms:
    if perm not in settings['permissions']['allow']:
        settings['permissions']['allow'].append(perm)

settings.setdefault('hooks', {})

# PreToolUse hooks
settings['hooks'].setdefault('PreToolUse', [])
pre_hooks = {
    'Write|Edit': 'bash "\$HOME/.claude/hooks/secrets-check.sh"',
    'Bash': 'bash "\$HOME/.claude/hooks/dangerous-cmd-check.sh"',
}
for matcher, cmd in pre_hooks.items():
    exists = any(
        h.get('matcher') == matcher and
        any(hh.get('command') == cmd for hh in h.get('hooks', []))
        for h in settings['hooks']['PreToolUse']
    )
    if not exists:
        settings['hooks']['PreToolUse'].append({
            'matcher': matcher,
            'hooks': [{'type': 'command', 'command': cmd, 'timeout': 10}]
        })

# PostToolUse hooks
settings['hooks'].setdefault('PostToolUse', [])
post_hooks = [
    ('Write|Edit', 'bash "\$HOME/.claude/hooks/file-size-check.sh"'),
    ('Write|Edit', 'bash "\$HOME/.claude/hooks/vault-lint.sh"'),
]
for matcher, cmd in post_hooks:
    exists = any(
        h.get('matcher') == matcher and
        any(hh.get('command') == cmd for hh in h.get('hooks', []))
        for h in settings['hooks']['PostToolUse']
    )
    if not exists:
        settings['hooks']['PostToolUse'].append({
            'matcher': matcher,
            'hooks': [{'type': 'command', 'command': cmd, 'timeout': 10}]
        })

# SessionStart hook
settings['hooks'].setdefault('SessionStart', [])
session_cmd = 'bash "\$HOME/.claude/hooks/compile-memory.sh"'
exists = any(
    any(hh.get('command') == session_cmd for hh in h.get('hooks', []))
    for h in settings['hooks']['SessionStart']
)
if not exists:
    settings['hooks']['SessionStart'].append({
        'matcher': 'startup|resume',
        'hooks': [{'type': 'command', 'command': session_cmd, 'timeout': 15}]
    })

with open(settings_path, 'w', encoding='utf-8') as f:
    json.dump(settings, f, indent=2)

print('  Settings merged successfully')
"@

python -c $settingsPy
if ($LASTEXITCODE -ne 0) {
    # Fall back to python3 if python is not found
    python3 -c $settingsPy
}

# ---------- Step 7b: Configure MCP ----------
Write-Host "[7/7] Configuring MCP server..." -ForegroundColor Yellow
$mcpPath = Join-Path $env:USERPROFILE ".claude\mcp.json"

$mcpPy = @"
import json, os

mcp_path = r'$mcpPath'
vault_path = '$vaultPathForward'

if os.path.exists(mcp_path):
    with open(mcp_path, encoding='utf-8') as f:
        mcp = json.load(f)
else:
    mcp = {}

mcp.setdefault('mcpServers', {})

if 'obsidian' not in mcp['mcpServers']:
    mcp['mcpServers']['obsidian'] = {
        'command': 'npx',
        'args': ['-y', '@bitbonsai/mcpvault@latest', vault_path]
    }
    print('  MCP obsidian server configured')
else:
    print('  MCP obsidian server already configured - skipping')

with open(mcp_path, 'w', encoding='utf-8') as f:
    json.dump(mcp, f, indent=2)
"@

python -c $mcpPy
if ($LASTEXITCODE -ne 0) {
    python3 -c $mcpPy
}

# Copy project mappings example
$projectMappings = Join-Path $env:USERPROFILE ".claude\rekall-projects.json"
if (-not (Test-Path $projectMappings)) {
    Copy-Item (Join-Path $PSScriptRoot "rekall-projects.json.example") $projectMappings -Force
}

# ---------- Done ----------
Write-Host ""
Write-Host "Rekall installed!" -ForegroundColor Green
Write-Host ""
Write-Host "  Vault:    $VaultPath"
Write-Host "  About:    About ${UserName}.md"
Write-Host "  Hooks:    ~/.claude/hooks/ (6 hooks)"
Write-Host "  Commands: ~/.claude/commands/ (4 commands)"
Write-Host "  Memory:   $MemoryDir"
Write-Host ""
Write-Host "Start a new Claude Code session - your past conversations will be processed automatically." -ForegroundColor Blue
Write-Host ""
Write-Host "  Commands available:"
Write-Host "    /session-log          - capture current session"
Write-Host "    /vault-health         - audit vault health"
Write-Host "    /vault-consolidate    - synthesize project knowledge"
Write-Host "    /instincts-review     - review memory system"
Write-Host ""
