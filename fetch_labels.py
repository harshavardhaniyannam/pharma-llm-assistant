"""Step 1: download one best-quality US label per pilot drug from openFDA.

Usage:
    python fetch_labels.py              # all pilot drugs
    python fetch_labels.py --only metformin
Output: data/raw/<drug>.json
"""
import argparse
import json
import time
from datetime import date

import requests

from config import OPENFDA_API_KEY, RAW_DIR, SECTION_FIELDS
from drugs import PILOT_DRUGS, slugify

API_URL = "https://api.fda.gov/drug/label.json"


def has_text(label: dict, field: str) -> bool:
    value = label.get(field)
    return bool(value) and any(isinstance(x, str) and x.strip() for x in value)


def score_label(label: dict, us_name: str) -> tuple:
    """Higher is better: single-ingredient > more sections filled > Rx > newer."""
    ofda = label.get("openfda", {})
    generics = [g.lower() for g in ofda.get("generic_name", [])]
    single = len(generics) == 1 and us_name.lower() in generics[0]
    rx = "HUMAN PRESCRIPTION DRUG" in ofda.get("product_type", [])
    n_sections = sum(
        any(has_text(label, f) for f in fields) for fields in SECTION_FIELDS.values()
    )
    return (single, n_sections, rx, label.get("effective_time", ""))


def query_openfda(us_name: str, limit: int = 25) -> list:
    params = {"search": f'openfda.generic_name:"{us_name}"', "limit": limit}
    if OPENFDA_API_KEY:
        params["api_key"] = OPENFDA_API_KEY
    for attempt in range(3):
        resp = requests.get(API_URL, params=params, timeout=60)
        if resp.status_code == 404:        # openFDA returns 404 for "no matches"
            return []
        if resp.status_code == 429:        # rate limited
            time.sleep(5 * (attempt + 1))
            continue
        resp.raise_for_status()
        return resp.json().get("results", [])
    raise RuntimeError("openFDA rate limit hit repeatedly; try again later")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="fetch just one drug (generic_name)")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    drugs = [d for d in PILOT_DRUGS if not args.only or d["generic_name"] == args.only]
    if not drugs:
        raise SystemExit(f"No drug named {args.only!r} in drugs.py")

    for d in drugs:
        name, us_name = d["generic_name"], d["us_name"]
        try:
            results = query_openfda(us_name)
        except Exception as exc:  # keep going if one drug fails
            print(f"[FAIL] {name}: {exc}")
            continue
        if not results:
            print(f"[MISS] {name}: no labels found for {us_name!r}")
            continue
        best = max(results, key=lambda lab: score_label(lab, us_name))
        out = {
            "generic_name": name,
            "us_name": us_name,
            "fetched_on": date.today().isoformat(),
            "label": best,
        }
        (RAW_DIR / f"{slugify(name)}.json").write_text(
            json.dumps(out, ensure_ascii=False), encoding="utf-8"
        )
        print(f"[OK]   {name}: set_id={best.get('set_id')} "
              f"date={best.get('effective_time')} (from {len(results)} candidates)")
        time.sleep(0.4)


if __name__ == "__main__":
    main()
