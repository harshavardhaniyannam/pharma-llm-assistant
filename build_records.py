"""Step 3: merge the label + all extra sources into one structured record per drug.

Usage: python build_records.py
Input : data/raw/<drug>.json (required), data/extra/<drug>.json (optional)
Output: data/records/<drug>.json   (+ a coverage table printed to the screen)

Every section keeps its own source (name, date, url) so answers can cite correctly.
"""
import json
import re
from datetime import date

from config import (EXTRA_DIR, IGNORE_LABEL_FIELDS, RAW_DIR, RECORDS_DIR, SECTION_FIELDS,
                    SECTION_ORDER)
from drugs import PILOT_DRUGS, slugify


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def fmt_date(yyyymmdd: str) -> str:
    if yyyymmdd and len(yyyymmdd) == 8:
        return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"
    return yyyymmdd or "unknown"


def _texts(label: dict, field: str) -> list:
    value = label.get(field)
    if not isinstance(value, list):
        return []
    return [clean(t) for t in value if isinstance(t, str) and clean(t)]


def build_label_sections(label: dict) -> dict:
    """Mapped sections + a catch-all 'other' so no label text is lost."""
    sections, used = {}, set()
    for section, fields in SECTION_FIELDS.items():
        parts, seen = [], set()
        for field in fields:
            used.add(field)
            for t in _texts(label, field):
                if t not in seen:
                    seen.add(t)
                    parts.append(t)
        if parts:
            sections[section] = "\n\n".join(parts)
    other = []
    for field in sorted(label):
        if field in used or field in IGNORE_LABEL_FIELDS or field.endswith("_table"):
            continue
        for t in _texts(label, field):
            other.append(f"[{field.replace('_', ' ')}] {t}")
    if other:
        sections["other"] = "\n\n".join(other)
    return sections


def _join(items):
    return ", ".join(str(i) for i in items if i)


def build_extra_sections(d: dict, label: dict, extra: dict, today: str):
    """Sections made from non-label sources. Returns (sections, section_sources)."""
    ofda = label.get("openfda", {})
    rx, ch, pc = extra.get("rxnorm", {}), extra.get("chembl", {}), extra.get("pubchem", {})
    fa, wk = extra.get("faers", {}), extra.get("wikipedia", {})
    secs, srcs = {}, {}

    # --- identifiers & classification
    atc_codes = ch.get("atc_codes") or []
    atc_names = [f"{a['code']} ({a['name']})" for a in rx.get("atc_classes", [])]
    p = [f"{d['generic_name']} (US label name: {d['us_name']})."]
    if d.get("note"):
        p.append("Note: " + d["note"])
    if rx.get("rxcui"):
        p.append(f"RxNorm ingredient RxCUI: {rx['rxcui']}.")
    if atc_codes:
        p.append("WHO ATC code(s): " + _join(atc_codes) + ".")
    if atc_names:
        p.append("ATC classes (RxClass): " + _join(atc_names) + ".")
    for key, title in (("pharm_class_epc", "Established pharmacologic class"),
                       ("pharm_class_moa", "Mechanism-of-action class"),
                       ("pharm_class_pe", "Physiologic effect"),
                       ("pharm_class_cs", "Chemical structure class")):
        if ofda.get(key):
            p.append(f"{title} (FDA): {_join(ofda[key])}.")
    if ofda.get("unii"):
        p.append("UNII: " + _join(ofda["unii"][:3]) + ".")
    if pc.get("cas"):
        p.append(f"CAS number: {pc['cas']}.")
    if ch.get("chembl_id"):
        p.append(f"ChEMBL ID: {ch['chembl_id']}.")
    if pc.get("cid"):
        p.append(f"PubChem CID: {pc['cid']}.")
    if ch.get("first_approval_year"):
        p.append(f"First approval year (ChEMBL): {ch['first_approval_year']}.")
    brands_us = sorted(set(ofda.get("brand_name", [])) | set(rx.get("brands_us", [])))
    if brands_us:
        p.append("US brand names: " + _join(brands_us[:20]) + ".")
    if d.get("brands_india"):
        p.append("Indian brand names (unverified seed list): " + _join(d["brands_india"]) + ".")
    if d.get("aliases"):
        p.append("Also known as: " + _join(d["aliases"]) + ".")
    if len(p) > 1:
        secs["identifiers"] = " ".join(p)
        srcs["identifiers"] = {"name": "RxNorm / ChEMBL / PubChem / FDA label",
                               "date": today, "url": "https://rxnav.nlm.nih.gov/"}

    # --- chemistry
    c = []
    if pc.get("formula"):
        c.append(f"Molecular formula: {pc['formula']}.")
    mw = pc.get("molecular_weight") or ch.get("properties", {}).get("full_mwt")
    if mw:
        c.append(f"Molecular weight: {mw} g/mol.")
    if pc.get("iupac_name"):
        c.append(f"IUPAC name: {pc['iupac_name']}.")
    if pc.get("xlogp") is not None:
        c.append(f"XLogP (lipophilicity, PubChem): {pc['xlogp']}.")
    if pc.get("tpsa") is not None:
        c.append(f"Topological polar surface area: {pc['tpsa']}.")
    pr = ch.get("properties", {})
    if pr.get("hba") is not None or pr.get("hbd") is not None:
        c.append(f"H-bond acceptors: {pr.get('hba')}, donors: {pr.get('hbd')} (ChEMBL).")
    if ch.get("smiles"):
        c.append(f"SMILES: {ch['smiles']}.")
    if pc.get("synonyms"):
        c.append("Synonyms: " + _join(pc["synonyms"][:15]) + ".")
    if c:
        secs["chemistry"] = " ".join(c)
        cid = pc.get("cid")
        srcs["chemistry"] = {"name": "PubChem / ChEMBL", "date": today,
                             "url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}" if cid
                             else "https://pubchem.ncbi.nlm.nih.gov/"}

    # --- mechanism and targets (ChEMBL)
    mech = []
    for m in ch.get("mechanisms", []):
        t = m.get("target") or {}
        line = f"Mechanism of action (ChEMBL): {m.get('mechanism') or 'not stated'}."
        if m.get("action_type"):
            line += f" Action type: {m['action_type']}."
        if t.get("name"):
            line += f" Target: {t['name']}" + (f" ({t.get('type')}, {t.get('organism')})" if t.get("type") else "") + "."
        mech.append(line)
    if mech:
        secs["mechanism_targets"] = " ".join(mech)
        srcs["mechanism_targets"] = {"name": "ChEMBL", "date": today,
                                     "url": f"https://www.ebi.ac.uk/chembl/compound_report_card/{ch['chembl_id']}/"}

    # --- indications recorded in ChEMBL
    if ch.get("indications"):
        items = [f"{i['term']} (phase {int(i['max_phase'])})" for i in ch["indications"]]
        secs["chembl_indications"] = (
            "Indications recorded in ChEMBL (development phase 3 or above): " + _join(items) + ". "
            "These come from curated sources and may include non-US uses; the FDA label is the "
            "reference for US-approved indications.")
        srcs["chembl_indications"] = srcs.get("mechanism_targets") or {
            "name": "ChEMBL", "date": today,
            "url": f"https://www.ebi.ac.uk/chembl/compound_report_card/{ch['chembl_id']}/"}

    # --- FAERS
    if fa.get("top_reactions"):
        top = _join(f"{r['term']} ({r['count']})" for r in fa["top_reactions"])
        secs["faers"] = (
            f"FDA Adverse Event Reporting System (FAERS) via openFDA: about {fa.get('total_reports')} "
            f"reports mention {d['us_name']}. Most frequently reported reaction terms (number of reports): "
            f"{top}. Caution: these are spontaneous reports. They do not prove the drug caused the event "
            f"and cannot be used to estimate how common a side effect is.")
        srcs["faers"] = {"name": "FDA FAERS via openFDA", "date": today,
                         "url": "https://open.fda.gov/data/faers/"}

    # --- Wikipedia overview and history
    if wk.get("intro"):
        secs["overview"] = wk["intro"]
        srcs["overview"] = {"name": "Wikipedia (CC BY-SA)", "date": today, "url": wk.get("url", "")}
    if wk.get("history"):
        secs["history"] = wk["history"]
        srcs["history"] = {"name": "Wikipedia (CC BY-SA)", "date": today, "url": wk.get("url", "")}
    return secs, srcs


def main():
    RECORDS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"{'drug':20} {'label':>5} {'extra':>5}  extra sources found")
    for d in PILOT_DRUGS:
        slug = slugify(d["generic_name"])
        raw_path = RAW_DIR / f"{slug}.json"
        if not raw_path.exists():
            print(f"{d['generic_name']:20} (no raw label; run fetch_labels.py)")
            continue
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        label = raw["label"]
        extra_path = EXTRA_DIR / f"{slug}.json"
        extra = json.loads(extra_path.read_text(encoding="utf-8")) if extra_path.exists() else {}
        today = raw.get("fetched_on", date.today().isoformat())
        set_id = label.get("set_id", "")
        label_src = {"name": "US FDA label", "date": fmt_date(label.get("effective_time", "")),
                     "url": f"https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={set_id}"}

        label_secs = build_label_sections(label)
        extra_secs, extra_srcs = build_extra_sections(d, label, extra, today)
        sections = {**label_secs, **extra_secs}
        sections = {k: sections[k] for k in SECTION_ORDER if k in sections}
        section_sources = {k: (extra_srcs[k] if k in extra_srcs else label_src) for k in sections}

        ofda = label.get("openfda", {})
        rx, ch, pc = extra.get("rxnorm", {}), extra.get("chembl", {}), extra.get("pubchem", {})
        record = {
            "generic_name": d["generic_name"],
            "us_name": d["us_name"],
            "aliases": d.get("aliases", []),
            "note": d.get("note", ""),
            "brands_india": d.get("brands_india", []),
            "brands_us": sorted(set(ofda.get("brand_name", [])) | set(rx.get("brands_us", []))),
            "identifiers": {
                "rxcui": rx.get("rxcui"),
                "atc_codes": ch.get("atc_codes", []),
                "atc_classes": rx.get("atc_classes", []),
                "pharm_class": {k: ofda.get(f"pharm_class_{k}", []) for k in ("epc", "moa", "pe", "cs")},
                "unii": ofda.get("unii", []),
                "cas": pc.get("cas"),
                "chembl_id": ch.get("chembl_id"),
                "pubchem_cid": pc.get("cid"),
            },
            "patient_info_links": extra.get("medlineplus", []),
            "sections": sections,
            "section_sources": section_sources,
            "source": {**label_src, "country": "US", "set_id": set_id},
            "retrieved_on": today,
        }
        (RECORDS_DIR / f"{slug}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        found = [k for k in ("rxnorm", "chembl", "pubchem", "faers", "wikipedia") if extra.get(k)]
        print(f"{d['generic_name']:20} {len(label_secs):>5} {len(extra_secs):>5}  {', '.join(found) or '-'}")


if __name__ == "__main__":
    main()
