"""Step 5: score the system on your test questions.

Usage (from project root):
    python eval/run_eval.py             # retrieval metrics only (no LLM needed)
    python eval/run_eval.py --generate  # also check generated answers

IMPORTANT: the sample keywords in test_questions.csv were written without seeing
your downloaded labels. Read the real label text and fix them. Then add your own
questions (aim for 30+, include look-alike names and dangerous cases).
"""
import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rag import DrugRAG  # noqa: E402


def split(field):
    return [x.strip().lower() for x in (field or "").split("|") if x.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--generate", action="store_true")
    args = ap.parse_args()

    rag = DrugRAG()
    here = Path(__file__).resolve().parent
    rows = list(csv.DictReader(open(here / "test_questions.csv", encoding="utf-8")))
    results, passed = [], 0

    for row in rows:
        q = row["question"]
        exp_drug, exp_sec = row["expected_drug"], row["expected_section"]
        must, must_not = split(row["must_contain"]), split(row["must_not_contain"])
        out = rag.answer(q) if args.generate else None
        hits = out["hits"] if out else rag.retrieve(q)
        blob = " ".join(h["text"] for h in hits).lower()
        if args.generate:
            blob += " " + out["answer"].lower()

        if exp_drug == "NONE":
            ok, notes = (len(hits) == 0), "expected 'not found'"
        else:
            drug_ok = bool(hits) and hits[0]["meta"]["drug"] == exp_drug
            sec_ok = (not exp_sec) or any(h["meta"]["section"] == exp_sec for h in hits)
            kw_ok = all(k in blob for k in must)
            bad = [k for k in must_not if k in blob]
            ok = drug_ok and sec_ok and kw_ok and not bad
            notes = f"top1_drug={drug_ok} section_in_topk={sec_ok} keywords={kw_ok} forbidden={bad}"
        passed += ok
        results.append({"id": row["id"], "question": q, "pass": ok, "notes": notes})
        print(f"[{'PASS' if ok else 'FAIL'}] #{row['id']} {q}\n        {notes}")

    print(f"\nScore: {passed}/{len(rows)} = {100 * passed / len(rows):.0f}%")
    with open(here / "results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "question", "pass", "notes"])
        w.writeheader()
        w.writerows(results)
    print("Saved eval/results.csv")


if __name__ == "__main__":
    main()
