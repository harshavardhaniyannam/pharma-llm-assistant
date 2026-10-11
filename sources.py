"""Free public data sources, one function each. Every function returns a plain dict
(empty if nothing found) and NEVER raises, so one failing source cannot stop the pipeline.

  rxnorm()      NLM RxNav: ingredient RxCUI, ATC classes, US brand names
  chembl()      EMBL-EBI ChEMBL: ids, ATC, properties, mechanism, targets, indications
  pubchem()     NCBI PubChem: formula, weight, IUPAC name, XLogP, synonyms, CAS
  faers()       openFDA FAERS: report totals and most frequent reaction terms
  wikipedia()   Wikipedia: overview and history text (CC BY-SA, keep attribution)
  medlineplus() MedlinePlus Connect: patient-information links (links only)

Not included on purpose: DrugBank (restrictive license) and any scraped site.
"""
import re
import time
from urllib.parse import quote

import requests

from config import OPENFDA_API_KEY, USER_AGENT

HEADERS = {"User-Agent": USER_AGENT}
RXNAV = "https://rxnav.nlm.nih.gov/REST"
CHEMBL = "https://www.ebi.ac.uk/chembl/api/data"
PUBCHEM = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
OPENFDA_EVENT = "https://api.fda.gov/drug/event.json"


def get_json(url, params=None, retries=3, timeout=45):
    """GET -> parsed JSON, or None on 404 / repeated failure."""
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
        except requests.RequestException:
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 404:
            return None
        if r.status_code == 429:
            time.sleep(5 * (attempt + 1))
            continue
        if r.ok:
            try:
                return r.json()
            except ValueError:
                return None
        time.sleep(2)
    return None


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------- RxNorm
def rxnorm(name: str) -> dict:
    try:
        data = get_json(f"{RXNAV}/rxcui.json", {"name": name})
        ids = (data or {}).get("idGroup", {}).get("rxnormId", [])
        if not ids:
            return {}
        rxcui = ids[0]
        atc, seen = [], set()
        d = get_json(f"{RXNAV}/rxclass/class/byRxcui.json", {"rxcui": rxcui, "relaSource": "ATC"})
        for info in (d or {}).get("rxclassDrugInfoList", {}).get("rxclassDrugInfo", []) or []:
            item = info.get("rxclassMinConceptItem", {})
            code = item.get("classId")
            if code and code not in seen:
                seen.add(code)
                atc.append({"code": code, "name": item.get("className")})
        brands = set()
        d = get_json(f"{RXNAV}/rxcui/{rxcui}/related.json", {"tty": "BN"})
        for grp in (d or {}).get("relatedGroup", {}).get("conceptGroup", []) or []:
            for c in grp.get("conceptProperties", []) or []:
                if c.get("name"):
                    brands.add(c["name"])
        return {"rxcui": rxcui, "atc_classes": atc, "brands_us": sorted(brands)[:40]}
    except Exception:
        return {}


# ---------------------------------------------------------------- ChEMBL
def _chembl_find(names):
    best = None
    for n in names:                                   # 1) exact preferred name
        d = get_json(f"{CHEMBL}/molecule.json", {"pref_name__iexact": n, "limit": 5})
        mols = (d or {}).get("molecules", [])
        if mols:
            return max(mols, key=lambda m: _f(m.get("max_phase")))
    for n in names:                                   # 2) fall back to synonym search
        d = get_json(f"{CHEMBL}/molecule/search.json", {"q": n, "limit": 10})
        for m in (d or {}).get("molecules", []):
            syns = {(s.get("molecule_synonym") or "").lower() for s in m.get("molecule_synonyms") or []}
            if n.lower() in syns or (m.get("pref_name") or "").lower() == n.lower():
                if best is None or _f(m.get("max_phase")) > _f(best.get("max_phase")):
                    best = m
        if best:
            return best
    return None


def chembl(names: list) -> dict:
    try:
        mol = _chembl_find(names)
        if not mol:
            return {}
        cid = mol["molecule_chembl_id"]
        props = mol.get("molecule_properties") or {}
        structs = mol.get("molecule_structures") or {}
        out = {
            "chembl_id": cid,
            "pref_name": mol.get("pref_name"),
            "max_phase": _f(mol.get("max_phase")),
            "first_approval_year": mol.get("first_approval"),
            "black_box_flag": mol.get("black_box_warning"),
            "molecule_type": mol.get("molecule_type"),
            "atc_codes": mol.get("atc_classifications") or [],
            "properties": {k: props.get(k) for k in
                           ("full_mwt", "alogp", "hba", "hbd", "psa", "rtb") if props.get(k) is not None},
            "smiles": structs.get("canonical_smiles"),
            "inchi_key": structs.get("standard_inchi_key"),
        }
        # mechanisms and targets
        d = get_json(f"{CHEMBL}/mechanism.json", {"molecule_chembl_id": cid, "limit": 50})
        mechs = (d or {}).get("mechanisms", []) or []
        tids = sorted({m["target_chembl_id"] for m in mechs if m.get("target_chembl_id")})
        tnames = {}
        if tids:
            td = get_json(f"{CHEMBL}/target.json", {"target_chembl_id__in": ",".join(tids), "limit": 50})
            for t in (td or {}).get("targets", []) or []:
                tnames[t["target_chembl_id"]] = {"name": t.get("pref_name"),
                                                 "type": t.get("target_type"),
                                                 "organism": t.get("organism")}
        out["mechanisms"] = [{
            "mechanism": m.get("mechanism_of_action"),
            "action_type": m.get("action_type"),
            "target": tnames.get(m.get("target_chembl_id"), {}),
        } for m in mechs]
        # indications (phase >= 3 only, to cut noise)
        d = get_json(f"{CHEMBL}/drug_indication.json", {"molecule_chembl_id": cid, "limit": 200})
        inds = {}
        for i in (d or {}).get("drug_indications", []) or []:
            term = i.get("mesh_heading") or i.get("efo_term")
            ph = _f(i.get("max_phase_for_ind"))
            if term and ph >= 3:
                inds[term] = max(ph, inds.get(term, 0))
        out["indications"] = [{"term": t, "max_phase": p}
                              for t, p in sorted(inds.items(), key=lambda kv: (-kv[1], kv[0]))][:25]
        return out
    except Exception:
        return {}


# ---------------------------------------------------------------- PubChem
def pubchem(names: list) -> dict:
    try:
        props = "MolecularFormula,MolecularWeight,IUPACName,XLogP,TPSA,InChIKey"
        row = None
        for n in names:
            d = get_json(f"{PUBCHEM}/compound/name/{quote(n)}/property/{props}/JSON")
            rows = (d or {}).get("PropertyTable", {}).get("Properties", [])
            if rows:
                row = rows[0]
                break
            time.sleep(0.3)
        if not row:
            return {}
        cid = row.get("CID")
        syn = get_json(f"{PUBCHEM}/compound/cid/{cid}/synonyms/JSON")
        info = (syn or {}).get("InformationList", {}).get("Information") or [{}]
        syns = info[0].get("Synonym", []) or []
        cas = next((s for s in syns if re.fullmatch(r"\d{2,7}-\d{2}-\d", s)), None)
        seen, clean = set(), []
        for s in syns:
            if (re.fullmatch(r"[A-Za-z][A-Za-z0-9 \-]{2,40}", s) and not re.search(r"\d{3,}", s)
                    and s.lower() not in seen):
                seen.add(s.lower())
                clean.append(s)
        return {"cid": cid, "formula": row.get("MolecularFormula"),
                "molecular_weight": row.get("MolecularWeight"), "iupac_name": row.get("IUPACName"),
                "xlogp": row.get("XLogP"), "tpsa": row.get("TPSA"), "inchi_key": row.get("InChIKey"),
                "cas": cas, "synonyms": clean[:25]}
    except Exception:
        return {}


# ---------------------------------------------------------------- FAERS
def faers(us_name: str, top_n: int = 20) -> dict:
    try:
        base = {"api_key": OPENFDA_API_KEY} if OPENFDA_API_KEY else {}
        search = f'patient.drug.openfda.generic_name:"{us_name}"'
        tot = get_json(OPENFDA_EVENT, {**base, "search": search, "limit": 1})
        total = (tot or {}).get("meta", {}).get("results", {}).get("total")
        cnt = get_json(OPENFDA_EVENT, {**base, "search": search,
                                       "count": "patient.reaction.reactionmeddrapt.exact",
                                       "limit": top_n})
        reactions = [{"term": r["term"], "count": r["count"]}
                     for r in (cnt or {}).get("results", []) or []]
        if not total and not reactions:
            return {}
        return {"total_reports": total, "top_reactions": reactions}
    except Exception:
        return {}


# ---------------------------------------------------------------- Wikipedia
def wikipedia(title: str) -> dict:
    try:
        d = get_json("https://en.wikipedia.org/w/api.php", {
            "action": "query", "prop": "extracts", "explaintext": 1, "redirects": 1,
            "titles": title, "format": "json", "exsectionformat": "wiki"})
        pages = (d or {}).get("query", {}).get("pages", {})
        page = next(iter(pages.values()), None)
        if not page or "missing" in page:
            return {}
        text = page.get("extract", "") or ""
        intro = text.split("\n== ")[0].strip()
        m = re.search(r"\n==\s*History[^=\n]*==\n(.*?)(?=\n==[^=]|\Z)", text, re.DOTALL)
        history = re.sub(r"\n{2,}", "\n\n", m.group(1)).strip() if m else ""
        t = page.get("title", title)
        return {"title": t, "url": f"https://en.wikipedia.org/wiki/{quote(t.replace(' ', '_'))}",
                "intro": intro[:2500], "history": history[:4000]}
    except Exception:
        return {}


# ---------------------------------------------------------------- MedlinePlus
def medlineplus(rxcui: str) -> list:
    """Patient-information links only (we do not copy their text)."""
    try:
        d = get_json("https://connect.medlineplus.gov/service", {
            "mainSearchCriteria.v.cs": "2.16.840.1.113883.6.88",
            "mainSearchCriteria.v.c": rxcui,
            "knowledgeResponseType": "application/json"})
        out = []
        for e in (d or {}).get("feed", {}).get("entry", []) or []:
            title = (e.get("title") or {}).get("_value")
            links = e.get("link") or [{}]
            href = links[0].get("href")
            if title and href:
                out.append({"title": title, "url": href})
        return out[:5]
    except Exception:
        return []
