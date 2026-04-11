# Instincts Review

Review your Rekall memory system. Use the `list_memories` and `forget` MCP tools to audit instincts.

## Process

1. Call `list_memories` with `type: "instinct"` to see all active instincts
2. For each instinct, show: content, confidence, evidence count, domain, last seen date
3. Group by domain
4. Flag any with low confidence (< 0.5) as candidates for removal
5. Flag any contradictions (the compiler detects these - check MEMORY.md for `[!conflict]` callouts)
6. Ask the user what to do with each flagged instinct:
   - **Keep** - no change
   - **Boost** - use `remember` with `source: "user-explicit"` to reinforce it
   - **Remove** - use `forget` to archive it
   - **Merge** - if two instincts say the same thing, `forget` one and `remember` a combined version

## After Review

Run `rekall-compile` to regenerate MEMORY.md with the updated instincts.
