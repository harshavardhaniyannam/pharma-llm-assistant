# Pharma Drug Information Assistant (RAG)

An educational prototype that answers pharmacist-style drug questions from **official US FDA
drug labels plus other free public databases**, with source citations and a **rules-based
interaction checker**. It also builds a complete "drug profile" for every drug.

> **Safety notice:** This is a learning project. It supports, and does not replace, clinical
> judgment. Always verify with official references. Not for clinical use.

## What information is collected per drug

| Information | Source | Notes |
|---|---|---|
| Indications, dosing text, contraindications, warnings, boxed warning, adverse reactions, interaction text, special populations, pharmacology, clinical studies, toxicology, abuse/dependence, overdose, composition, patient counseling, storage, plus every other label section | openFDA / DailyMed (US label) | Primary, citable source with label date |
| RxNorm ID, ATC classes, US brand names | NLM RxNav / RxClass | Free |
| FDA pharmacologic classes, UNII | openFDA label fields | |
| ChEMBL ID, ATC codes, first-approval year, mechanism of action, targets, phase 3+ indications | ChEMBL (EMBL-EBI) | CC BY-SA licence: keep attribution |
| Formula, molecular weight, IUPAC name, XLogP, TPSA, CAS, synonyms | PubChem (NCBI) | Free |
| Most frequently reported adverse events | FDA FAERS via openFDA | Reports only: not incidence, not proof of causation |
| Overview and history | Wikipedia | CC BY-SA, background only, verify facts |
| Patient-information links | MedlinePlus Connect | Links only |
| Indian brands, India-vs-US notes | `drugs.py` (you) | Seed list: verify yourself |
| Interaction severity and management | `data/interactions_curated.json` (you) | Draft: verify before use |

Not used: **DrugBank** (restrictive licence) and scraped websites. Sources like CDSCO and the
NLEM are not available as clean APIs, so add them by hand or from downloaded files later.

## How it works

```
openFDA labels + RxNorm + ChEMBL + PubChem + FAERS + Wikipedia
        -> one structured record per drug (each section keeps its own source and date)
        -> chunks + embeddings (ChromaDB)
question -> detect drug names / intent -> retrieve -> LLM answers ONLY from retrieved text
                     |
                     +-> curated interaction table (rules engine; the LLM never decides interactions)
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Optional: edit `USER_AGENT` in `config.py` (or set the `USER_AGENT` environment variable) to
include your email, as Wikipedia and NCBI ask API users to identify themselves.

## Run the pipeline

```bash
python fetch_labels.py            # 1. FDA labels            -> data/raw/
python fetch_extras.py            # 2. other databases       -> data/extra/
python build_records.py           # 3. merge into records    -> data/records/
python build_index.py             # 4. chunk + embed + store -> data/chroma/
streamlit run app.py              # 5. app (Ask tab + Drug profile tab)
python eval/run_eval.py           # 6. score your test questions
python drug_profile.py --all      # optional: Markdown profile for every drug -> data/profiles/
```

`fetch_extras.py` prints a table showing which sources found each drug. `build_records.py` prints
how many label sections and extra sections each drug got. Check both for gaps.

## Choose how answers are generated (optional)

| Option | How |
|---|---|
| Retrieval only (default, free) | Nothing to set; the app shows the best passages |
| Anthropic API | `export ANTHROPIC_API_KEY=...` (optionally `LLM_MODEL=...`) |
| Local model via Ollama | Install Ollama, `ollama pull llama3.1:8b`, then `export LLM_PROVIDER=ollama` |

## Your to-do list (this is where your pharmacy knowledge matters)

1. Verify the Indian brand names in `drugs.py`; add `aliases` and `note` fields where India and the US differ (see methimazole/carbimazole).
2. Review every entry in `data/interactions_curated.json` against BNF / Stockley's / Micromedex,
   then set `reviewed: true` and fill `source`.
3. Read the downloaded profiles and fix the keywords in `eval/test_questions.csv`; grow it to 30+
   questions including look-alike names, renal/pregnancy cases and out-of-scope drugs.
4. Tune `MAX_DISTANCE` in `config.py` using your eval results.
5. Record your final score and failure cases below.

## Results

_(fill in after evaluation: number of questions, accuracy, unsafe errors found, what you fixed)_

## Limitations

- Core clinical text is from US labels: Indian brands, strengths and practice may differ.
- Only the drugs in `drugs.py` are covered.
- The interaction table is small and hand-curated.
- Non-label sources can disagree with the label; the assistant is told to prefer the label.
- Labels change often; re-run the pipeline to refresh.

## Data and licensing

openFDA/DailyMed and RxNav are US government data. ChEMBL and Wikipedia are CC BY-SA
(attribution required). PubChem data is public but individual records can carry source terms.
Check each source's terms before reusing data. Raw data is not stored in this repository.
