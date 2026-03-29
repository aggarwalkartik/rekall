# Session Log

Capture what happened in this conversation as an Obsidian vault session note.

## Instructions

1. **Review the conversation** — Read through everything discussed in this session.

2. **Extract the following categories** (skip any that don't apply):

   - **Projects touched**: Which projects were worked on? What changed?
   - **Decisions made**: Any "we chose X over Y because Z" moments → create/update Decisions/ notes
   - **Things learned**: Technical discoveries, how-tos, gotchas → create/update Research/ notes
   - **Ideas**: Things discussed but not yet acted on → create/update Ideas/ notes
   - **Personal observations**: Anything revealing about the user's preferences, opinions, personality → update the About file in your vault root
   - **Open questions**: Unresolved items to pick up next time
   - **Next steps**: What should happen next

3. **Create or append to today's session note** at `Sessions/YYYY-MM-DD.md`:

   If creating new:
   ```yaml
   ---
   date: YYYY-MM-DD
   tags: [session]
   status: active
   summary: "Session log for YYYY-MM-DD"
   ---
   ```

   If the file already exists (multiple sessions in one day), append a new section with a timestamp header.

   Structure each session entry as:

   ```markdown
   ## Session — HH:MM

   ### Projects Touched
   - [[Project Hub]] — what was done

   ### Decisions Made
   - Created [[Decision Note]] — brief description

   ### Learned
   - Brief description of learning → see [[Research Note]] if created

   ### Ideas
   - Brief description → see [[Idea Note]] if created

   ### Open Questions
   - Question that wasn't resolved

   ### Next Steps
   - What to do next
   ```

4. **Update AGENDA.md** in the vault root (Vault path: as configured in your CLAUDE.md):
   - Replace `## Active Workstreams` with current active projects (based on this session + previous agenda)
   - Replace `## Open Questions` with unresolved items from this session
   - Replace `## Blocked` with any blockers identified
   - Replace `## Pick Up Here` with context for the next session
   - Update the `Last updated` timestamp in the blockquote

5. **Update project hubs** — For each project touched, add a link to today's session note in the project hub if not already linked.

6. **Create standalone notes** — If a decision, learning, or idea is substantial enough (more than 1-2 sentences), create it as its own note in the proper folder with full frontmatter, tags, Parent: link, and link it from the session note.

7. **Update the About file** — If any personal observations were captured, append them to the appropriate section of the About file in your vault root.

8. **Present a summary** — Show what was captured:
   - Session note created/updated
   - AGENDA.md changes
   - Standalone notes created/updated (with [[wikilinks]])
   - Any observations added to the About file
