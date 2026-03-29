# Vault Consolidate

Synthesize all research and decision notes for a given project into a knowledge framework note.

## Usage

The argument after the command is the project name. It must match a note in `Projects/`.

Example: `/vault-consolidate My Project`

## Instructions

Vault path: as configured in your CLAUDE.md

1. **Read the project hub** — Find and read `Projects/{argument}.md`. If it doesn't exist, list available project hubs and stop.

2. **Find all related notes**:
   - Notes linked from the project hub
   - Notes with `Parent: [[{argument}]]` in content
   - Notes mentioning `[[{argument}]]` anywhere
   - Search Research/ and Decisions/ for the project name in content

3. **Read all related notes** — Skip `status: archived` notes.

4. **Create synthesis note** at `Research/{Project Name} Knowledge Synthesis.md`:

   ```yaml
   ---
   date: YYYY-MM-DD
   tags: [research, {domain-tag from project hub}]
   status: active
   summary: "Synthesized knowledge framework for {Project Name}"
   ---
   ```

   Structure:
   ```markdown
   # {Project Name} Knowledge Synthesis
   > [!summary]
   > Synthesis of N research notes and M decision notes for [[{Project Name}]].

   Parent: [[{Project Name}]]

   ## Key Findings
   - Finding — sources: [[Note A]], [[Note B]]
   (Group by theme. Note convergence across sources.)

   ## Decisions Made
   - [[Decision Note]] — what was chosen and why
   (Chronological. Note superseded decisions.)

   ## Contradictions & Tensions
   - [[Note A]] says X, but [[Note B]] says Y
   (Only if actual contradictions exist.)

   ## Knowledge Gaps
   - Topics mentioned but never researched
   - Questions raised but never answered

   ## Open Questions
   - Questions from reading all notes together

   ## Sources
   - All N+M notes with dates
   ```

5. **Update project hub** — Add link to synthesis note.

6. **Present summary** — Notes synthesized, findings count, contradictions, gaps.
