"""Step 5: Streamlit app.   Run:  streamlit run app.py"""
import json

import streamlit as st

from config import RECORDS_DIR
from drug_profile import TITLES, render_markdown
from rag import DrugRAG

st.set_page_config(page_title="Pharma Drug Assistant", page_icon="💊", layout="wide")


@st.cache_resource
def load_rag():
    return DrugRAG()


@st.cache_data
def load_records():
    recs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(RECORDS_DIR.glob("*.json"))]
    return {r["generic_name"]: r for r in recs}


st.title("💊 Pharma Drug Information Assistant")
st.caption("Educational prototype. Answers come from US FDA labels, public databases and a curated "
           "rules table. It supports pharmacists and does not replace clinical judgment. "
           "Verify with official references.")

tab_ask, tab_profile = st.tabs(["Ask a question", "Drug profile (all information)"])

# ------------------------------------------------------------------ Ask
with tab_ask:
    try:
        rag = load_rag()
    except Exception as exc:
        st.error(f"Could not start the assistant: {exc}")
        st.stop()

    examples = [
        "",
        "What are the contraindications of metformin?",
        "Can I give warfarin with ibuprofen?",
        "What is the boxed warning for warfarin?",
        "Is Glycomet the same as metformin? What are its side effects?",
        "Can pregnant women take metoprolol?",
        "What is the molecular weight and ATC code of fluconazole?",
        "Tell me the history of aspirin",
    ]
    choice = st.selectbox("Try an example", examples)
    question = st.text_input("Ask about a drug", value=choice, placeholder="e.g. side effects of amlodipine")

    if question:
        with st.spinner("Searching..."):
            result = rag.answer(question)

        if result["drugs"]:
            st.write("**Drugs detected:** " + ", ".join(result["drugs"]))

        for r in result["rules"]:
            a, b = r["pair"]
            e = r["entry"]
            if e:
                tag = "reviewed" if e.get("reviewed") else "draft, not yet reviewed"
                st.warning(f"**Rule engine: {a} + {b}** | severity: **{e['severity']}** ({tag})\n\n"
                           f"{e['effect']}\n\n*Management:* {e['management']}")
            else:
                st.info(f"**Rule engine: {a} + {b}**: no curated entry. "
                        "This does not mean the combination is safe.")

        st.subheader("Answer")
        st.write(result["answer"])
        if result["mode"] == "none":
            st.caption("Retrieval-only mode. Set ANTHROPIC_API_KEY (or LLM_PROVIDER=ollama) for generated answers.")

        if result["hits"]:
            st.subheader("Sources")
            for i, h in enumerate(result["hits"], 1):
                m = h["meta"]
                with st.expander(f"[{i}] {m['drug']} | {m['section']} | {m['source_name']} "
                                 f"{m['source_date']} | distance {h['distance']:.2f}"):
                    st.write(h["text"])
                    if m.get("url"):
                        st.markdown(f"[Open source]({m['url']})")

# ------------------------------------------------------------------ Profile
with tab_profile:
    records = load_records()
    if not records:
        st.info("No records yet. Run the pipeline first (see README).")
    else:
        name = st.selectbox("Choose a drug", sorted(records))
        rec = records[name]
        ids = rec.get("identifiers", {})
        c1, c2, c3 = st.columns(3)
        c1.metric("ATC", ", ".join(ids.get("atc_codes", [])[:3]) or "n/a")
        c2.metric("RxCUI", ids.get("rxcui") or "n/a")
        c3.metric("Label date", rec["source"]["date"])
        if rec.get("note"):
            st.info(rec["note"])
        if rec.get("brands_india"):
            st.write("**Indian brands (unverified):** " + ", ".join(rec["brands_india"]))
        if rec.get("brands_us"):
            st.write("**US brands:** " + ", ".join(rec["brands_us"][:15]))
        st.download_button("Download full profile (Markdown)", render_markdown(rec),
                           file_name=f"{name}.md", mime="text/markdown")
        for section, text in rec["sections"].items():
            src = rec.get("section_sources", {}).get(section, {})
            with st.expander(TITLES.get(section, section)):
                st.caption(f"Source: {src.get('name', 'unknown')}, {src.get('date', '')}")
                st.write(text)
                if src.get("url"):
                    st.markdown(f"[Open source]({src['url']})")
        for l in rec.get("patient_info_links", []):
            st.markdown(f"- [{l['title']}]({l['url']}) (MedlinePlus)")
