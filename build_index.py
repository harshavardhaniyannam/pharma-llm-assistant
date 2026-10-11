"""Step 3: chunk records, embed them, and store them in ChromaDB.

Usage: python build_index.py   (re-run whenever records change)
"""
import json
import re

from config import (CHROMA_DIR, CHUNK_CHARS, CHUNK_OVERLAP, COLLECTION_NAME,
                    EMBED_MODEL, RECORDS_DIR)
from drugs import slugify


def chunk_text(text: str, size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= size:
        return [text] if text else []
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):                      # prefer to cut at a sentence end
            cut = text.rfind(". ", start + size // 2, end)
            if cut != -1:
                end = cut + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def build_chunks(record: dict) -> list:
    """One dict per chunk: id, document (with header), metadata. Each section carries its own source."""
    out = []
    for section, text in record["sections"].items():
        src = record.get("section_sources", {}).get(section) or record["source"]
        for i, piece in enumerate(chunk_text(text)):
            header = (f"[Drug: {record['generic_name']} | Section: {section} | "
                      f"Source: {src['name']}, {src['date']}]")
            out.append({
                "id": f"{slugify(record['generic_name'])}:{section}:{i}",
                "document": f"{header}\n{piece}",
                "metadata": {
                    "drug": record["generic_name"],
                    "section": section,
                    "source_name": src["name"],
                    "source_date": src["date"],
                    "url": src.get("url", ""),
                    "chunk_index": i,
                },
            })
    return out


def main():
    import chromadb
    from sentence_transformers import SentenceTransformer

    files = sorted(RECORDS_DIR.glob("*.json"))
    if not files:
        raise SystemExit("No records found. Run fetch_labels.py and build_records.py first.")
    chunks = []
    for f in files:
        chunks += build_chunks(json.loads(f.read_text(encoding="utf-8")))
    print(f"{len(files)} records -> {len(chunks)} chunks")

    print(f"Loading embedding model {EMBED_MODEL} (first run downloads it)...")
    model = SentenceTransformer(EMBED_MODEL)

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    col = client.create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})

    batch = 64
    for i in range(0, len(chunks), batch):
        part = chunks[i:i + batch]
        embs = model.encode([c["document"] for c in part], normalize_embeddings=True).tolist()
        col.add(ids=[c["id"] for c in part],
                documents=[c["document"] for c in part],
                metadatas=[c["metadata"] for c in part],
                embeddings=embs)
        print(f"  indexed {min(i + batch, len(chunks))}/{len(chunks)}")
    print("Done. Index stored in", CHROMA_DIR)


if __name__ == "__main__":
    main()
