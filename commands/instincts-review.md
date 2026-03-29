# Instincts Review

Review and maintain the instincts memory system.

## Instructions

1. **Read instincts** — Read your project's memory/instincts.jsonl file.

2. **Calculate effective confidence** — Apply decay: -0.05 per 30 days since `last_seen`.

3. **Present grouped by health**:

   ### Healthy (effective confidence >= 0.7)
   | ID | Pattern | Confidence | Last Seen | Source |
   |----|---------|-----------|-----------|--------|

   ### Fading (0.4 - 0.7)
   | ID | Pattern | Confidence | Effective | Last Seen | Days Since |
   |----|---------|-----------|-----------|-----------|------------|

   ### At Risk (0.2 - 0.4)
   | ID | Pattern | Confidence | Effective | Last Seen | Days Since |
   |----|---------|-----------|-----------|-----------|------------|

   ### Recently Added (created in last 14 days)
   | ID | Pattern | Confidence | Source |
   |----|---------|-----------|--------|

4. **For Fading and At Risk instincts, ask**:
   - **Confirm**: Bump `last_seen` to today, increment `evidence_count`, bump confidence by 0.1 (cap 0.7 for observed, 0.9 for explicit)
   - **Dismiss**: Remove the instinct from the file
   - **Adjust**: Change pattern text or confidence level

5. **Show stats**: Total, by source, by domain, average age, average confidence.

6. **Recompile MEMORY.md** after any changes by running your project's memory compile script.
