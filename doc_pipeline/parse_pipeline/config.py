"""
doc_pipeline/parse_pipeline/config.py
======================================
All configuration for the parsing pipeline.
Reads from environment; falls back to sensible defaults.
"""
from __future__ import annotations
import json
import os
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent.parent   # doc_pipeline/
DATA_DIR   = BASE_DIR / "data"
LOGS_DIR   = BASE_DIR / "logs"
DB_PATH    = DATA_DIR / "resumes.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ── OCR ───────────────────────────────────────────────────────────────────────
OCR_CONFIDENCE_THRESHOLD = float(os.getenv("OCR_CONFIDENCE_THRESHOLD", "0.60"))
OCR_DPI                  = int(os.getenv("OCR_DPI", "150"))
MIN_TEXT_CHARS_PER_PAGE  = int(os.getenv("MIN_TEXT_CHARS_PER_PAGE", "20"))
GARBLE_RATIO_THRESHOLD   = float(os.getenv("GARBLE_RATIO_THRESHOLD", "0.30"))

# ── spaCy ─────────────────────────────────────────────────────────────────────
SPACY_MODEL = os.getenv("SPACY_MODEL", "en_core_web_sm")

# ── SLM ───────────────────────────────────────────────────────────────────────
SLM_ENABLED      = os.getenv("SLM_ENABLED", "false").lower() == "true"
SLM_PROVIDER     = os.getenv("SLM_PROVIDER", "gemini_free")   # gemini_free | groq | local
GEMINI_API_KEY   = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY     = os.getenv("GROQ_API_KEY", "")

# ── Rejection rules ───────────────────────────────────────────────────────────
RULES_PATH = Path(__file__).parent / "rules" / "rejection_rules.json"

def load_rejection_rules() -> dict:
    with RULES_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)

REJECTION_RULES = load_rejection_rules()

# ── Chroma / FAISS ────────────────────────────────────────────────────────────
CHROMA_PATH       = DATA_DIR / "chroma"
FAISS_INDEX_PATH  = DATA_DIR / "faiss" / "resumes.index"
EMBEDDING_MODEL   = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")