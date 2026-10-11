"""Rules engine: interactions come from a curated table, NOT from the LLM."""
import json
from itertools import combinations
from pathlib import Path

from config import INTERACTIONS_FILE


def load_interactions(path=INTERACTIONS_FILE) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {frozenset(d.lower() for d in e["drugs"]): e for e in data.get("interactions", [])}


def check_interactions(drug_names, table=None) -> list:
    """Check every pair. Returns [{'pair': (a, b), 'entry': dict | None}, ...]."""
    table = load_interactions() if table is None else table
    names = sorted({n.lower() for n in drug_names})
    return [{"pair": (a, b), "entry": table.get(frozenset((a, b)))}
            for a, b in combinations(names, 2)]


def format_for_prompt(results: list) -> str:
    lines = []
    for r in results:
        a, b = r["pair"]
        e = r["entry"]
        if e is None:
            lines.append(f"- {a} + {b}: NO curated entry. This does NOT mean the combination is safe.")
        else:
            status = "reviewed" if e.get("reviewed") else "DRAFT, not yet reviewed"
            lines.append(f"- {a} + {b}: severity={e['severity']} ({status}). "
                         f"Effect: {e['effect']} Management: {e['management']}")
    return "\n".join(lines)
