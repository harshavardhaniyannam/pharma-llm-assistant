"""Step 2: collect extra information from other free sources for every drug.

Usage:
    python fetch_extras.py              # all drugs
    python fetch_extras.py --only metformin
Output: data/extra/<drug>.json
"""
import argparse
import json
import time
from datetime import date

import sources
from config import EXTRA_DIR
from drugs import PILOT_DRUGS, lookup_names, slugify


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="fetch just one drug (generic_name)")
    args = ap.parse_args()

    EXTRA_DIR.mkdir(parents=True, exist_ok=True)
    drugs = [d for d in PILOT_DRUGS if not args.only or d["generic_name"] == args.only]
    if not drugs:
        raise SystemExit(f"No drug named {args.only!r} in drugs.py")

    print(f"{'drug':20} rxnorm chembl pubchem faers wiki  medline")
    for d in drugs:
        names = lookup_names(d)
        rx = {}
        for n in names:                      # try each name until RxNorm recognises one
            rx = sources.rxnorm(n)
            if rx:
                break
        extra = {
            "fetched_on": date.today().isoformat(),
            "rxnorm": rx,
            "chembl": sources.chembl(names),
            "pubchem": sources.pubchem(names),
            "faers": sources.faers(d["us_name"]),
            "wikipedia": sources.wikipedia(d.get("wiki_title") or d["generic_name"].title()),
            "medlineplus": sources.medlineplus(rx["rxcui"]) if rx.get("rxcui") else [],
        }
        (EXTRA_DIR / f"{slugify(d['generic_name'])}.json").write_text(
            json.dumps(extra, indent=2, ensure_ascii=False), encoding="utf-8")
        flag = lambda v: "yes" if v else "-"
        print(f"{d['generic_name']:20} {flag(rx):6} {flag(extra['chembl']):6} {flag(extra['pubchem']):7} "
              f"{flag(extra['faers']):5} {flag(extra['wikipedia']):5} {flag(extra['medlineplus'])}")
        time.sleep(0.5)


if __name__ == "__main__":
    main()
