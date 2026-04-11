"""Compile MEMORY.md from SQLite memories table."""
from __future__ import annotations
import math
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from rekall.storage import Storage

POSITIVE_SIGNALS = {"always", "use", "prefer", "ensure", "must", "include", "add"}
NEGATIVE_SIGNALS = {"never", "don't", "avoid", "skip", "without", "stop", "not", "no"}
STOPWORDS = {"a", "an", "the", "is", "are", "was", "were", "in", "on", "at", "to", "for", "of", "and", "or", "it", "that", "this"}


def effective_confidence(confidence: float, days_since: float, evidence_count: int) -> float:
    return confidence * math.exp(-days_since / (60 * math.sqrt(max(evidence_count, 1))))


def jaccard_similarity(tokens_a: set[str], tokens_b: set[str]) -> float:
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def tokenize(text: str) -> set[str]:
    words = set(re.findall(r'\w+', text.lower()))
    return words - STOPWORDS


def detect_contradictions(memories: list[dict]) -> list[tuple[str, str, str, str]]:
    """Find potential contradictions between memories in the same domain."""
    conflicts = []
    for i, a in enumerate(memories):
        for b in memories[i + 1:]:
            if a.get("domain") != b.get("domain"):
                continue
            tokens_a = tokenize(a["content"])
            tokens_b = tokenize(b["content"])
            if jaccard_similarity(tokens_a, tokens_b) < 0.3:
                continue
            words_a = set(a["content"].lower().split())
            words_b = set(b["content"].lower().split())
            a_has_pos = bool(words_a & POSITIVE_SIGNALS)
            a_has_neg = bool(words_a & NEGATIVE_SIGNALS)
            b_has_pos = bool(words_b & POSITIVE_SIGNALS)
            b_has_neg = bool(words_b & NEGATIVE_SIGNALS)
            if (a_has_pos and b_has_neg) or (a_has_neg and b_has_pos):
                conflicts.append((a["id"], b["id"], a["content"], b["content"]))
    return conflicts


def compile_memory_md(db: Storage, output_path: Path) -> None:
    """Compile MEMORY.md from SQLite memories."""
    now = datetime.now()
    memories = db.list_memories(type="instinct", limit=500)

    # Compute effective confidence and filter
    active = []
    for mem in memories:
        last_seen = datetime.fromisoformat(mem.last_seen_at)
        days = (now - last_seen).days
        eff = effective_confidence(mem.confidence, days, mem.evidence_count)
        if eff >= 0.2:
            active.append({
                "id": mem.id,
                "content": mem.content,
                "domain": mem.domain or "general",
                "confidence": mem.confidence,
                "effective": eff,
                "evidence_count": mem.evidence_count,
            })

    # Group by domain
    groups: dict[str, list] = defaultdict(list)
    for mem in active:
        groups[mem["domain"]].append(mem)

    # Sort within groups by effective confidence descending
    for domain in groups:
        groups[domain].sort(key=lambda m: m["effective"], reverse=True)

    # Detect contradictions
    conflicts = detect_contradictions(active)

    # Render
    lines = ["# Rekall Memory", ""]

    if conflicts:
        for a_id, b_id, a_content, b_content in conflicts:
            lines.append(f"> [!conflict] {a_id} vs {b_id}")
            lines.append(f'> "{a_content}" conflicts with "{b_content}"')
            lines.append("")

    for domain in sorted(groups.keys()):
        lines.append(f"## {domain.replace('-', ' ').title()}")
        lines.append("")
        for mem in groups[domain]:
            marker = ""
            if mem["effective"] < 0.4:
                marker = "[L] "
            elif mem["effective"] < 0.7:
                marker = "[M] "
            lines.append(f"- {marker}{mem['content']}")
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))


def main():
    """Entry point for rekall-compile."""
    from rekall.config import get_config
    config = get_config()
    db = Storage(config.db_path)
    db.initialize()
    try:
        output = config.memory_md_path or config.data_dir / "MEMORY.md"
        compile_memory_md(db, output)
        print(f"Compiled MEMORY.md to {output}", file=__import__("sys").stderr)
    finally:
        db.close()


if __name__ == "__main__":
    main()
