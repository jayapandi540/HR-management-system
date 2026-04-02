"""
doc_pipeline/parse_pipeline/storage/db_client.py
=================================================
SQLite persistence for parsed resumes.

Two JSON blobs per resume:
  masked_json  — PII replaced with placeholders ([NAME], [EMAIL], …)
                 Safe to pass to Project 3 / 4 matching and ranking.
  pii_json     — Full data including name/email/phone.
                 Restricted access — Project 2 ORM controls who can read it.

Tables
------
  resumes   (id, external_id, masked_json, pii_json, created_at, ocr_used, page_count)
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional

from doc_pipeline.parse_pipeline.config import DATA_DIR
from doc_pipeline.parse_pipeline.serialization.schema import ResumeDocument

logger = logging.getLogger("parse_pipeline.db")

DB_PATH = DATA_DIR / "resumes.db"


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init_tables() -> None:
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS resumes (
                id           TEXT PRIMARY KEY,
                external_id  TEXT,
                masked_json  TEXT NOT NULL,
                pii_json     TEXT NOT NULL,
                created_at   TEXT DEFAULT (datetime('now')),
                ocr_used     INTEGER DEFAULT 0,
                page_count   INTEGER DEFAULT 0,
                total_years  REAL DEFAULT 0.0,
                status       TEXT DEFAULT 'complete'
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_resumes_ext ON resumes(external_id)")
    logger.debug("SQLite tables ready at %s", DB_PATH)


# Initialise on import
_init_tables()


def store_resume(
    resume_doc: ResumeDocument,
    raw_text_for_vector: str = "",
) -> tuple[Path, Path]:
    """
    Persist a ResumeDocument to SQLite.

    Writes:
      data/masked/<resume_id>.json  — PII-safe version
      data/pii/<resume_id>.json     — full PII version

    Returns (masked_path, pii_path).
    """
    masked_dir = DATA_DIR / "masked"
    pii_dir    = DATA_DIR / "pii"
    masked_dir.mkdir(parents=True, exist_ok=True)
    pii_dir.mkdir(parents=True, exist_ok=True)

    masked_data = resume_doc.to_masked_dict()
    pii_data    = resume_doc.to_pii_dict()

    masked_path = masked_dir / f"{resume_doc.resume_id}.json"
    pii_path    = pii_dir    / f"{resume_doc.resume_id}.json"

    masked_path.write_text(json.dumps(masked_data, indent=2, default=str), encoding="utf-8")
    pii_path.write_text(   json.dumps(pii_data,    indent=2, default=str), encoding="utf-8")

    with _get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO resumes
              (id, external_id, masked_json, pii_json, ocr_used, page_count, total_years)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            resume_doc.resume_id,
            resume_doc.external_id,
            json.dumps(masked_data, default=str),
            json.dumps(pii_data,    default=str),
            int(resume_doc.ocr_used),
            resume_doc.page_count,
            resume_doc.total_years_exp,
        ))

    logger.info("Stored resume %s (masked=%s)", resume_doc.resume_id, masked_path.name)
    return masked_path, pii_path


def load_masked(resume_id: str) -> Optional[dict]:
    """Load the masked (PII-safe) resume dict from SQLite."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT masked_json FROM resumes WHERE id = ?", (resume_id,)
        ).fetchone()
    return json.loads(row[0]) if row else None


def load_pii(resume_id: str) -> Optional[dict]:
    """Load the full PII resume dict from SQLite. Restrict to authorised callers."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT pii_json FROM resumes WHERE id = ?", (resume_id,)
        ).fetchone()
    return json.loads(row[0]) if row else None