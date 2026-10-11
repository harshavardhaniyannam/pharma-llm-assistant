"""Retrieval + answer generation for the pharma assistant."""
import json
import os
import re

import requests

from config import (CHROMA_DIR, COLLECTION_NAME, EMBED_MODEL, LLM_MODEL, LLM_PROVIDER,
                    MAX_DISTANCE, OLLAMA_MODEL, QUERY_PREFIX, RECORDS_DIR, TOP_K)
from rules import check_interactions, format_for_prompt, load_interactions

SYSTEM_PROMPT = """You are a drug-information assistant supporting pharmacists.
Rules:
1. Answer ONLY from the numbered SOURCES provided. Do not use outside knowledge.
2. Cite sources inline like [1], [2], and name the source type when it matters
   (FDA label, ChEMBL, PubChem, FAERS, Wikipedia). Mention the date for doses and warnings.
3. If the sources do not contain the answer, reply exactly: "Not found in the loaded drug labels."
4. Never invent doses, numbers, or interactions. Keep numbers exactly as written in the sources.
5. The FDA label is the reference for approved uses, doses, contraindications and warnings.
   If another source disagrees with the label, say so and prefer the label.
6. FAERS counts are spontaneous reports: never present them as how common a side effect is.
   Wikipedia text is background only, not clinical guidance.
7. If a RULE ENGINE RESULT is provided, it is authoritative for interaction severity. Explain it; never contradict it.
8. If a drug record has a note about India vs US differences, mention it when relevant.
9. Be concise. End with: "Verify with official references before clinical use."
"""

INTENT_SECTIONS = {
    "adverse_reactions": ["side effect", "adverse", "reaction", "toxicity"],
    "interactions": ["interact", "combine", "together with", "taken with", "along with", "with food"],
    "contraindications": ["contraindic", "should not be used", "who should not", "not be given"],
    "dosage": ["dose", "dosage", "how much", "how to take", "how often", "administration"],
    "indications": ["used for", "indication", "what is it for", "uses of", "treat"],
    "mechanism": ["mechanism", "how does", "how do", "pharmacology", "mode of action",
                  "target", "receptor", "enzyme"],
    "special_populations": ["pregnan", "breastfeed", "lactation", "pediatric", "children",
                            "elderly", "geriatric", "renal", "kidney", "hepatic", "liver"],
    "warnings": ["warning", "precaution", "caution"],
    "boxed_warning": ["boxed", "black box"],
    "overdosage": ["overdose", "poison"],
    "storage": ["storage", "store ", "supplied"],
    "history": ["history", "discovered", "invented", "origin", "who developed", "when was it"],
    "chemistry": ["formula", "molecular weight", "structure", "logp", "iupac", "chemical name",
                  "smiles", "cas number"],
    "identifiers": ["atc", "classification", "drug class", "class of", "rxnorm",
                    "pharmacologic class", "brand name", "brand"],
    "faers": ["faers", "reported", "real-world", "adverse event report", "most common reaction"],
    "composition": ["inactive ingredient", "excipient", "composition", "contains", "ingredients"],
    "patient_counseling": ["counsel", "patient information", "tell the patient",
                           "medication guide", "how should i take"],
    "clinical_studies": ["clinical trial", "clinical stud", "efficacy"],
    "nonclinical_toxicology": ["carcinogen", "fertility", "mutagen", "toxicology"],
    "abuse_dependence": ["dependence", "abuse", "addiction", "controlled substance", "withdrawal"],
    "overview": ["tell me about", "overview", "describe", "summary of", "what is "],
}
# When an intent matches, also search these related sections.
RELATED_SECTIONS = {
    "mechanism": ["mechanism_targets", "pharmacodynamics"],
    "indications": ["chembl_indications"],
    "adverse_reactions": ["faers"],
    "warnings": ["boxed_warning"],
}


# ---------- small helpers (no heavy imports, easy to test) -----------------
def load_records() -> list:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(RECORDS_DIR.glob("*.json"))]


def build_alias_map(records: list) -> dict:
    """alias (lowercase) -> generic_name. Aliases shorter than 4 chars are skipped
    to avoid false matches (e.g. a brand called 'Pan')."""
    alias = {}
    for rec in records:
        g = rec["generic_name"]
        for n in [g, rec.get("us_name", "")] + rec.get("aliases", []) + rec.get("brands_india", []):
            n = (n or "").strip().lower()
            if len(n) >= 4:
                alias[n] = g
    return alias


def detect_drugs(question: str, alias_map: dict) -> list:
    q = question.lower()
    found = []
    for alias, g in sorted(alias_map.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", q) and g not in found:
            found.append(g)
    return found


def detect_sections(question: str) -> list:
    q = question.lower()
    sections = [s for s, kws in INTENT_SECTIONS.items() if any(k in q for k in kws)]
    for s in list(sections):
        for extra in RELATED_SECTIONS.get(s, []):
            if extra not in sections:
                sections.append(extra)
    return sections


def build_prompt(question: str, hits: list, rule_results: list) -> str:
    sources = "\n\n".join(f"[{i}]\n{h['text']}" for i, h in enumerate(hits, 1))
    rules = ""
    if rule_results:
        rules = f"\n\nRULE ENGINE RESULT (authoritative):\n{format_for_prompt(rule_results)}"
    return f"SOURCES:\n{sources}{rules}\n\nQUESTION: {question}"


# ---------- main class ------------------------------------------------------
class DrugRAG:
    def __init__(self):
        import chromadb
        from sentence_transformers import SentenceTransformer

        self.records = load_records()
        if not self.records:
            raise RuntimeError("No records found. Run the data pipeline first (see README).")
        self.alias_map = build_alias_map(self.records)
        self.record_by_drug = {r["generic_name"]: r for r in self.records}
        self.interactions = load_interactions()
        self.embedder = SentenceTransformer(EMBED_MODEL)
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self.collection = client.get_collection(COLLECTION_NAME)

    # -- retrieval ---------------------------------------------------------
    def _query(self, qemb, drug, sections, n):
        conds = []
        if drug:
            conds.append({"drug": drug})
        if sections:
            conds.append({"section": {"$in": sections}})
        where = None if not conds else (conds[0] if len(conds) == 1 else {"$and": conds})
        res = self.collection.query(query_embeddings=qemb, n_results=n, where=where)
        docs, metas, dists = res["documents"][0], res["metadatas"][0], res["distances"][0]
        return [{"text": t, "meta": m, "distance": d}
                for t, m, d in zip(docs, metas, dists) if d <= MAX_DISTANCE]

    def retrieve(self, question: str, top_k: int = TOP_K, drugs: list = None) -> list:
        drugs = detect_drugs(question, self.alias_map) if drugs is None else drugs
        sections = detect_sections(question)
        qemb = self.embedder.encode([QUERY_PREFIX + question], normalize_embeddings=True).tolist()
        targets = drugs or [None]
        per_target = max(2, top_k // len(targets)) if drugs else top_k

        def run(secs):
            hits = []
            for d in targets:
                hits += self._query(qemb, d, secs, per_target)
            return hits

        hits = run(sections)
        if not hits and sections:          # intent guess was too narrow: retry without it
            hits = run([])
        hits.sort(key=lambda h: h["distance"])
        return hits[:max(top_k, len(targets) * 2)]

    # -- generation --------------------------------------------------------
    @staticmethod
    def provider() -> str:
        if LLM_PROVIDER:
            return LLM_PROVIDER
        return "anthropic" if os.getenv("ANTHROPIC_API_KEY") else "none"

    def _generate(self, prompt: str) -> str:
        provider = self.provider()
        if provider == "anthropic":
            import anthropic
            msg = anthropic.Anthropic().messages.create(
                model=LLM_MODEL, max_tokens=900, system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}])
            return "".join(b.text for b in msg.content if b.type == "text")
        if provider == "ollama":
            r = requests.post("http://localhost:11434/api/chat", timeout=300, json={
                "model": OLLAMA_MODEL, "stream": False,
                "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                             {"role": "user", "content": prompt}]})
            r.raise_for_status()
            return r.json()["message"]["content"]
        return "(No LLM configured: showing the most relevant label passages below.)"

    def answer(self, question: str, top_k: int = TOP_K) -> dict:
        drugs = detect_drugs(question, self.alias_map)
        hits = self.retrieve(question, top_k, drugs)
        rules = check_interactions(drugs, self.interactions) if len(drugs) >= 2 else []
        if not hits:
            text = "Not found in the loaded drug labels."
        else:
            text = self._generate(build_prompt(question, hits, rules))
        return {"answer": text, "hits": hits, "drugs": drugs, "rules": rules,
                "mode": self.provider()}
