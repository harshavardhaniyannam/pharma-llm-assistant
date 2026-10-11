"""Drug list for the project.

Required keys
  generic_name : name shown in the app
  us_name      : name used in US labels (openFDA search term)
  brands_india : Indian brands. Seed list from general knowledge: VERIFY every
                 brand yourself (CDSCO / CIMS / pharmacy references). Leave [] if unsure.
Optional keys
  aliases      : other names a user may type (also used for drug detection)
  note         : India-vs-US differences, shown in answers
  wiki_title   : Wikipedia article title if different from generic_name
  chembl_name  : name ChEMBL uses if different (ChEMBL uses INN names)
"""
import re

PILOT_DRUGS = [
    # --- Hypertension ---
    {"generic_name": "amlodipine", "us_name": "amlodipine", "brands_india": ["Amlokind", "Norvasc"]},
    {"generic_name": "telmisartan", "us_name": "telmisartan", "brands_india": ["Telma", "Telsartan"]},
    {"generic_name": "losartan", "us_name": "losartan", "brands_india": ["Losar", "Repace"]},
    {"generic_name": "enalapril", "us_name": "enalapril", "brands_india": ["Envas"]},
    {"generic_name": "metoprolol", "us_name": "metoprolol", "brands_india": ["Metolar", "Betaloc"]},
    {"generic_name": "hydrochlorothiazide", "us_name": "hydrochlorothiazide", "brands_india": []},
    # --- Thyroid ---
    {"generic_name": "levothyroxine", "us_name": "levothyroxine", "brands_india": ["Thyronorm", "Eltroxin"]},
    {"generic_name": "methimazole", "us_name": "methimazole", "brands_india": ["Neomercazole"],
     "aliases": ["carbimazole", "thiamazole"], "wiki_title": "Methimazole", "chembl_name": "thiamazole",
     "note": "India mainly uses carbimazole, a prodrug converted to methimazole. This record holds the "
             "US label for methimazole; confirm carbimazole-specific details with an Indian reference."},
    {"generic_name": "propylthiouracil", "us_name": "propylthiouracil", "brands_india": []},
    # --- Depression ---
    {"generic_name": "escitalopram", "us_name": "escitalopram", "brands_india": ["Nexito", "Stalopam"]},
    {"generic_name": "sertraline", "us_name": "sertraline", "brands_india": ["Daxid", "Serta"]},
    {"generic_name": "fluoxetine", "us_name": "fluoxetine", "brands_india": ["Fludac", "Prozac"]},
    {"generic_name": "amitriptyline", "us_name": "amitriptyline", "brands_india": ["Tryptomer"]},
    # --- Anxiety ---
    {"generic_name": "alprazolam", "us_name": "alprazolam", "brands_india": ["Alprax", "Restyl"]},
    {"generic_name": "clonazepam", "us_name": "clonazepam", "brands_india": ["Rivotril", "Clonotril", "Lonazep"]},
    {"generic_name": "lorazepam", "us_name": "lorazepam", "brands_india": ["Ativan"]},
    # --- Fever / pain ---
    {"generic_name": "paracetamol", "us_name": "acetaminophen", "brands_india": ["Crocin", "Dolo 650", "Calpol"],
     "aliases": ["acetaminophen"]},
    {"generic_name": "ibuprofen", "us_name": "ibuprofen", "brands_india": ["Brufen"]},
    # --- Viral infections ---
    {"generic_name": "acyclovir", "us_name": "acyclovir", "brands_india": ["Zovirax"], "aliases": ["aciclovir"]},
    {"generic_name": "oseltamivir", "us_name": "oseltamivir", "brands_india": ["Tamiflu", "Antiflu"]},
    # --- Fungal infections ---
    {"generic_name": "fluconazole", "us_name": "fluconazole", "brands_india": ["Forcan", "Zocon", "Diflucan"]},
    {"generic_name": "terbinafine", "us_name": "terbinafine", "brands_india": ["Lamisil"]},
    {"generic_name": "itraconazole", "us_name": "itraconazole", "brands_india": ["Sporanox", "Itaspor"]},
    # --- Common diseases ---
    {"generic_name": "metformin", "us_name": "metformin", "brands_india": ["Glycomet", "Glucophage"]},
    {"generic_name": "glimepiride", "us_name": "glimepiride", "brands_india": ["Amaryl", "Glimy"]},
    {"generic_name": "atorvastatin", "us_name": "atorvastatin", "brands_india": ["Atorva", "Lipitor"]},
    {"generic_name": "pantoprazole", "us_name": "pantoprazole", "brands_india": ["Pantocid", "Pan 40"]},
    {"generic_name": "cetirizine", "us_name": "cetirizine", "brands_india": ["Okacet", "Cetzine"]},
    {"generic_name": "salbutamol", "us_name": "albuterol", "brands_india": ["Asthalin"],
     "aliases": ["albuterol"], "wiki_title": "Salbutamol"},
    {"generic_name": "amoxicillin", "us_name": "amoxicillin", "brands_india": ["Mox", "Novamox"]},
    {"generic_name": "azithromycin", "us_name": "azithromycin", "brands_india": ["Azithral", "Azee"]},
    {"generic_name": "ciprofloxacin", "us_name": "ciprofloxacin", "brands_india": ["Ciplox", "Cifran"]},
    # --- Bleeding / clotting (interaction-heavy) ---
    {"generic_name": "warfarin", "us_name": "warfarin", "brands_india": ["Uniwarfin", "Warf"]},
    {"generic_name": "clopidogrel", "us_name": "clopidogrel", "brands_india": ["Clopitab", "Plavix"]},
    {"generic_name": "aspirin", "us_name": "aspirin", "brands_india": ["Ecosprin", "Disprin"]},
    # --- Optional look-alike pairs for safety testing (uncomment to add) ---
    # {"generic_name": "clonidine", "us_name": "clonidine", "brands_india": ["Catapres"]},
    # {"generic_name": "glipizide", "us_name": "glipizide", "brands_india": ["Glynase"]},
]


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def lookup_names(d: dict) -> list:
    """All names worth trying when searching other databases (deduplicated, in order)."""
    names = [d.get("chembl_name"), d["generic_name"], d["us_name"]] + d.get("aliases", [])
    seen, out = set(), []
    for n in names:
        if n and n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
    return out
