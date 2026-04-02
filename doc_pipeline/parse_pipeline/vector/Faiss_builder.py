"""
doc_pipeline/parse_pipeline/vector/faiss_builder.py
====================================================
Builds / updates a FAISS flat index from parsed resume embeddings.
Complement to Chroma: used for fast batch k-NN ranking across many resumes.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("parse_pipeline.faiss")

_FAISS_PATH  = Path("./data/faiss/resume.index")
_IDS_PATH    = Path("./data/faiss/resume_ids.json")
_index: Optional[object] = None
_ids:   list[str]        = []


def _load_index():
    global _index, _ids
    if _index is not None:
        return _index, _ids
    try:
        import faiss  # type: ignore
        from sentence_transformers import SentenceTransformer  # type: ignore
        dim = 384   # all-MiniLM-L6-v2

        if _FAISS_PATH.exists():
            _index = faiss.read_index(str(_FAISS_PATH))
            _ids   = json.loads(_IDS_PATH.read_text()) if _IDS_PATH.exists() else []
            logger.info("FAISS index loaded: %d vectors.", _index.ntotal)
        else:
            _FAISS_PATH.parent.mkdir(parents=True, exist_ok=True)
            _index = faiss.IndexFlatIP(dim)
            _ids   = []
    except ImportError as exc:
        logger.warning("FAISS/sentence-transformers not installed: %s", exc)
    return _index, _ids


def build_faiss() -> None:
    """Rebuild FAISS index from all resumes in SQLite."""
    from doc_pipeline.parse_pipeline.storage.db_client import _get_conn
    idx, ids = _load_index()
    if not idx:
        return

    import faiss  # type: ignore
    from sentence_transformers import SentenceTransformer  # type: ignore
    model = SentenceTransformer("all-MiniLM-L6-v2")

    conn = _get_conn()
    rows = conn.execute("SELECT id, masked_json FROM resumes").fetchall()
    texts, new_ids = [], []
    for rid, mj in rows:
        data = json.loads(mj)
        text = " ".join(s.get("cleaned_text","") for s in data.get("sections",[]))
        if text.strip():
            texts.append(text)
            new_ids.append(rid)

    if texts:
        import numpy as np
        vecs = model.encode(texts, normalize_embeddings=True).astype("float32")
        idx.add(vecs)
        _ids.extend(new_ids)
        faiss.write_index(idx, str(_FAISS_PATH))
        _IDS_PATH.write_text(json.dumps(_ids))
    logger.info("FAISS rebuilt: %d vectors.", len(_ids))


def update_faiss(resume_doc) -> None:
    """Incrementally add one resume to FAISS."""
    idx, ids = _load_index()
    if not idx:
        return
    try:
        import faiss, numpy as np  # type: ignore
        from sentence_transformers import SentenceTransformer  # type: ignore
        text = " ".join(s.cleaned_text for s in resume_doc.sections if s.cleaned_text)
        if not text.strip():
            return
        model = SentenceTransformer("all-MiniLM-L6-v2")
        vec   = model.encode([text], normalize_embeddings=True).astype("float32")
        idx.add(vec)
        ids.append(resume_doc.resume_id)
        faiss.write_index(idx, str(_FAISS_PATH))
        _IDS_PATH.write_text(json.dumps(ids))
    except Exception as exc:
        logger.debug("FAISS update failed: %s", exc)