# Vault Health Check

Run a comprehensive health audit of the Obsidian vault. This is a **read-only** operation — report findings, don't fix them.

## Instructions

Vault path: as configured in your CLAUDE.md

### Check 1: Orphan Detection
- Glob all .md files in the vault (all folders)
- For each file, grep the entire vault for `[[filename without .md]]`
- A note is orphaned if no other note links to it
- Home.md, the About file in your vault root, and AGENDA.md are excluded (allowed to have no incoming links)
- Report: list of orphan notes grouped by folder

### Check 2: Broken Wikilinks
- Grep all files for `\[\[.*?\]\]` patterns
- For each wikilink target, check if a matching .md file exists in any vault folder
- Report: list of broken links with source file and missing target

### Check 3: Frontmatter Compliance
- Read every note's frontmatter
- Check for required fields: date, tags, status, summary
- Check tags are from the allowed list: type tags (project, research, reference, decision, idea, session) and domain tags (as defined in your CLAUDE.md)
- Check status is one of: active, stale, archived
- Report: notes with missing/invalid fields, grouped by issue type

### Check 4: Template Adherence
- **Research/ notes**: Check for `> [!summary]` callout, `Parent:` link, `## Sources`, `## Related`
- **Decisions/ notes**: Check for `Parent:` link, `## Context`, `## Decision`, `## Consequences`
- **Ideas/ notes**: Check for `## Why This Could Work`, `## Open Questions`, `## Related`
- Report: adherence percentage per folder per field, list of non-compliant notes

### Check 5: Stale Note Detection
- Find project hubs with `status: stale` or `status: archived`
- Find research/decision notes linked to stale/archived projects but still marked `active`
- Report: candidates for status change

### Check 6: Duplicate Detection
- Group notes by similar titles (look for notes with overlapping keywords)
- For potential duplicates, read their summaries to confirm overlap
- Report: potential duplicate pairs with summaries

### Check 7: Missing Project Hubs
- Find clusters of 3+ Research/ notes that share wikilinks to the same non-existent target in Projects/
- Report: suggested project hubs to create with the notes that would link to them

### Check 8: Folder Misplacement
- Research-like notes in Projects/ (contains findings but isn't a hub with links to sub-notes)
- Decision-like notes in Research/ (contains "chose", "decided", "went with" + alternatives)
- Report: misplaced notes with suggested correct folder

### Check 9: Vault Stats
- Total notes per folder
- Tag distribution (count per tag)
- Most linked notes (top 10 by incoming link count)
- Notes with zero outgoing wikilinks

## Output Format

Present as a structured report:

```
## Vault Health Report — YYYY-MM-DD

### Critical (fix now)
| Issue | Count | Examples |
|-------|-------|---------|

### Warning (fix when convenient)
| Issue | Count | Examples |
|-------|-------|---------|

### Stats
| Metric | Value |
|--------|-------|

### Health Score: X/100
- Start at 100
- -2 per orphan note
- -3 per broken wikilink
- -1 per missing frontmatter field
- -1 per stale-but-active note
- -5 per missing project hub
- Floor at 0
```
