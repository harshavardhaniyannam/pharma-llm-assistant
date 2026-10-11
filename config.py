"""Central settings for the pharma RAG project."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RAW_DIR = DATA / "raw"
RECORDS_DIR = DATA / "records"
CHROMA_DIR = DATA / "chroma"
EXTRA_DIR = DATA / "extra"
PROFILES_DIR = DATA / "profiles"
INTERACTIONS_FILE = DATA / "interactions_curated.json"

# --- Retrieval settings -------------------------------------------------
COLLECTION_NAME = "drug_labels"
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
CHUNK_CHARS = 1200
CHUNK_OVERLAP = 150
TOP_K = 5
# Cosine distance (0 = identical). Chunks farther than this are ignored, and if
# nothing is left the app says "not found". Tune this using your eval set.
MAX_DISTANCE = 0.55

# --- LLM settings (all optional; app works in retrieval-only mode without) ---
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "")          # "anthropic" | "ollama" | "" = auto
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-5-5")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
OPENFDA_API_KEY = os.getenv("OPENFDA_API_KEY", "")     # optional, raises rate limits
# Wikipedia/NCBI ask API users to identify themselves. Put your own contact here.
USER_AGENT = os.getenv("USER_AGENT", "PharmaRAGLearningProject/1.0 (student project; contact: your-email@example.com)")

# --- Record template: our section name -> openFDA label fields ------------
# Rx labels use the first fields in each list, OTC labels use the later ones.
SECTION_FIELDS = {
    "boxed_warning": ["boxed_warning"],
    "description": ["description"],
    "indications": ["indications_and_usage", "purpose", "uses"],
    "dosage": ["dosage_and_administration", "directions"],
    "composition": ["active_ingredient", "inactive_ingredient", "dosage_forms_and_strengths"],
    "contraindications": ["contraindications"],
    "warnings": ["warnings_and_cautions", "warnings_and_precautions", "warnings",
                 "precautions", "general_precautions", "do_not_use", "ask_doctor",
                 "ask_doctor_or_pharmacist", "stop_use"],
    "adverse_reactions": ["adverse_reactions"],
    "interactions": ["drug_interactions", "drug_and_or_laboratory_test_interactions"],
    "special_populations": ["use_in_specific_populations", "pregnancy", "pediatric_use",
                            "geriatric_use", "nursing_mothers", "lactation",
                            "females_and_males_of_reproductive_potential"],
    "mechanism": ["mechanism_of_action", "clinical_pharmacology"],
    "pharmacodynamics": ["pharmacodynamics"],
    "pharmacokinetics": ["pharmacokinetics"],
    "clinical_studies": ["clinical_studies"],
    "nonclinical_toxicology": ["nonclinical_toxicology",
                               "carcinogenesis_and_mutagenesis_and_impairment_of_fertility",
                               "animal_pharmacology_and_or_toxicology"],
    "abuse_dependence": ["drug_abuse_and_dependence", "controlled_substance", "abuse", "dependence"],
    "overdosage": ["overdosage"],
    "laboratory_tests": ["laboratory_tests"],
    "patient_counseling": ["information_for_patients", "spl_patient_package_insert",
                           "spl_medguide", "patient_medication_information",
                           "instructions_for_use"],
    "storage": ["storage_and_handling", "how_supplied"],
}

# Label fields we never copy into the catch-all "other" section.
IGNORE_LABEL_FIELDS = {"id", "set_id", "version", "effective_time", "openfda",
                       "spl_product_data_elements", "package_label_principal_display_panel",
                       "principal_display_panel", "spl_indexing_data_elements"}

# Extra (non-label) sections created from other sources by build_records.py:
#   overview, history, identifiers, chemistry, mechanism_targets, chembl_indications, faers
SECTION_ORDER = ["overview", "identifiers", "description", "indications", "chembl_indications",
                 "dosage", "composition", "boxed_warning", "contraindications", "warnings",
                 "adverse_reactions", "faers", "interactions", "special_populations",
                 "mechanism", "mechanism_targets", "pharmacodynamics", "pharmacokinetics",
                 "chemistry", "clinical_studies", "nonclinical_toxicology", "abuse_dependence",
                 "overdosage", "laboratory_tests", "patient_counseling", "storage",
                 "history", "other"]
