"""
doc_pipeline/parse_pipeline/vector/chroma_builder.py
=====================================================
Builds / updates a Chroma vector collection from parsed resume sections.

Called by pipeline.py after store_resume() completes.
Uses SentenceTransformer (all-MiniLM-L6-v2) for embeddings.
"""
from __future__ import annotations

import logging
from typing import Optional

from doc_pipeline.parse_pipeline.serialization.schema import ResumeDocument

logger = logging.getLogger("parse_pipeline.chroma")

_CHROMA_PATH       = "./data/chroma"
_COLLECTION_NAME   = "resume_sections"
_client: Optional[object] = None
_collection: Optional[object] = None


def _get_collection():
    global _client, _collection
    if _collection is not None:
        return _collection
    try:
        import chromadb  # type: ignore
        from sentence_transformers import SentenceTransformer  # type: ignore
        _client     = chromadb.PersistentClient(path=_CHROMA_PATH)
        _collection = _client.get_or_create_collection(
            _COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("Chroma collection '%s' ready.", _COLLECTION_NAME)
    except ImportError as exc:
        logger.warning("Chroma/sentence-transformers not installed: %s", exc)
        return None
    return _collection


def build_chroma_collection() -> None:
    """Rebuild the entire Chroma collection from SQLite resumes.db."""
    from doc_pipeline.parse_pipeline.storage.db_client import _get_conn
    col = _get_collection()
    if not col:
        return

    conn = _get_conn()
    rows = conn.execute("SELECT id, masked_json FROM resumes").fetchall()
    import json
    for resume_id, masked_json in rows:
        data = json.loads(masked_json)
        sections = data.get("sections", [])
        for sec in sections:
            _upsert_section(col, resume_id, sec.get("heading","BODY"), sec.get("cleaned_text",""))
    logger.info("Chroma: rebuilt with %d resumes.", len(rows))


def update_chroma(resume_doc: ResumeDocument) -> None:
    """Incrementally add/update sections for one resume."""
    col = _get_collection()
    if not col:
        return
    for sec in resume_doc.sections:
        if sec.cleaned_text:
            _upsert_section(col, resume_doc.resume_id, sec.heading, sec.cleaned_text)


def _upsert_section(col, resume_id: str, heading: str, text: str) -> None:
    if not text.strip():
        return
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        model = SentenceTransformer("all-MiniLM-L6-v2")
        vec   = model.encode([text], normalize_embeddings=True)[0].tolist()
        doc_id = f"{resume_id}_{heading}"
        col.upsert(
            ids        = [doc_id],
            documents  = [text],
            embeddings = [vec],
            metadatas  = [{"resume_id": resume_id, "section": heading}],
        )
    except Exception as exc:
        logger.debug("Chroma upsert failed: %s", exc)