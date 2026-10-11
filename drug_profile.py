"""Full drug profile: everything we hold about one drug, as a Markdown document.

Usage:
    python drug_profile.py metformin          # print + save data/profiles/metformin.md
    python drug_profile.py --all              # save a profile for every drug
"""
import argparse
import json

from config import PROFILES_DIR, RECORDS_DIR
from drugs import slugify

TITLES = {
    "overview": "Overview", "identifiers": "Identifiers and classification",
    "description": "Description (label)", "indications": "Indications and usage",
    "chembl_indications": "Indications recorded in ChEMBL", "dosage": "Dosage and administration",
    "composition": "Composition and dosage forms", "boxed_warning": "Boxed warning",
    "contraindications": "Contraindications", "warnings": "Warnings and precautions",
    "adverse_reactions": "Adverse reactions (label)", "faers": "Reported adverse events (FAERS)",
    "interactions": "Drug interactions (label text)", "special_populations": "Use in specific populations",
    "mechanism": "Mechanism / clinical pharmacology (label)", "mechanism_targets": "Mechanism and targets (ChEMBL)",
    "pharmacodynamics": "Pharmacodynamics", "pharmacokinetics": "Pharmacokinetics",
    "chemistry": "Chemistry", "clinical_studies": "Clinical studies",
    "nonclinical_toxicology": "Nonclinical toxicology", "abuse_dependence": "Abuse and dependence",
    "overdosage": "Overdosage", "laboratory_tests": "Laboratory tests",
    "patient_counseling": "Patient counseling information", "storage": "Storage and supply",
    "history": "History", "other": "Other label sections",
}


def load_record(name: str) -> dict:
    path = RECORDS_DIR / f"{slugify(name)}.json"
    if not path.exists():
        raise SystemExit(f"No record for {name!r}. Run the pipeline first.")
    return json.loads(path.read_text(encoding="utf-8"))


def render_markdown(rec: dict) -> str:
    ids = rec.get("identifiers", {})
    out = [f"# {rec['generic_name'].title()}",
           f"*US label name: {rec['us_name']}. Educational use only; verify with official references.*"]
    if rec.get("note"):
        out.append(f"> **Note:** {rec['note']}")
    if rec.get("aliases"):
        out.append(f"**Also known as:** {', '.join(rec['aliases'])}")
    if rec.get("brands_india"):
        out.append(f"**Indian brands (unverified):** {', '.join(rec['brands_india'])}")
    if rec.get("brands_us"):
        out.append(f"**US brands:** {', '.join(rec['brands_us'][:15])}")
    facts = []
    if ids.get("rxcui"):
        facts.append(f"RxCUI {ids['rxcui']}")
    if ids.get("atc_codes"):
        facts.append("ATC " + ", ".join(ids["atc_codes"]))
    for k, v in (ids.get("pharm_class") or {}).items():
        if v:
            facts.append(f"{k.upper()}: {', '.join(v)}")
    for label, key in (("CAS", "cas"), ("ChEMBL", "chembl_id"), ("PubChem CID", "pubchem_cid")):
        if ids.get(key):
            facts.append(f"{label} {ids[key]}")
    if facts:
        out.append("**Identifiers:** " + " | ".join(facts))
    for section, text in rec["sections"].items():
        src = rec.get("section_sources", {}).get(section, {})
        out.append(f"## {TITLES.get(section, section)}")
        out.append(f"*Source: {src.get('name', 'unknown')}, {src.get('date', '')}"
                   + (f" ({src['url']})" if src.get("url") else "") + "*")
        out.append(text)
    if rec.get("patient_info_links"):
        out.append("## Patient information links (MedlinePlus)")
        out += [f"- [{l['title']}]({l['url']})" for l in rec["patient_info_links"]]
    return "\n\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("drug", nargs="?")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    if args.all:
        for p in sorted(RECORDS_DIR.glob("*.json")):
            rec = json.loads(p.read_text(encoding="utf-8"))
            (PROFILES_DIR / f"{p.stem}.md").write_text(render_markdown(rec), encoding="utf-8")
        print(f"Saved profiles to {PROFILES_DIR}")
    elif args.drug:
        md = render_markdown(load_record(args.drug))
        (PROFILES_DIR / f"{slugify(args.drug)}.md").write_text(md, encoding="utf-8")
        print(md)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
