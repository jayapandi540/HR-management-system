"""
doc_pipeline/parse_pipeline/storage/db_client.py
=================================================
SQLite resumes.db client.

Two JSON columns per resume row:
  masked_json  — PII removed; used for embedding, matching, display
  pii_json     — original PII preserved; should be encrypted at rest

Also stores gatekeeper_hits as a JSON column for audit.
"""
from __future__ import annotations
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from ..config import DB_PATH

_local = threading.local()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS resumes (
    id              TEXT PRIMARY KEY,
    external_id     TEXT,
    filename        TEXT,
    masked_json     TEXT NOT NULL,
    pii_json        TEXT NOT NULL,
    gatekeeper_json TEXT,
    ocr_used        INTEGER DEFAULT 0,
    quality         TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_resumes_external ON resumes(external_id);
CREATE INDEX IF NOT EXISTS idx_resumes_created  ON resumes(created_at);
"""


def _conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False,
                               detect_types=sqlite3.PARSE_DECLTYPES, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return _local.conn


@contextmanager
def get_db():
    conn = _conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(_SCHEMA)


def upsert_resume(
    resume_id:       str,
    masked_document: dict,
    pii_document:    dict,
    gatekeeper_hits: list,
    ocr_used:        bool = False,
    quality:         str  = "normal",
    external_id:     str  = "",
    filename:        str  = "",
) -> None:
    with get_db() as conn:
        conn.execute("""
            INSERT INTO resumes
              (id, external_id, filename, masked_json, pii_json, gatekeeper_json,
               ocr_used, quality, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              masked_json     = excluded.masked_json,
              pii_json        = excluded.pii_json,
              gatekeeper_json = excluded.gatekeeper_json,
              ocr_used        = excluded.ocr_used,
              quality         = excluded.quality,
              updated_at      = excluded.updated_at
        """, (
            resume_id, external_id, filename,
            json.dumps(masked_document, default=str),
            json.dumps(pii_document,    default=str),
            json.dumps(gatekeeper_hits, default=str),
            int(ocr_used), quality,
            datetime.utcnow().isoformat(),
        ))


def fetch_resume(resume_id: str) -> dict | None:
    conn = _conn()
    row  = conn.execute("SELECT * FROM resumes WHERE id = ?", (resume_id,)).fetchone()
    if not row:
        return None
    return {
        "id":           row["id"],
        "external_id":  row["external_id"],
        "masked":       json.loads(row["masked_json"]),
        "pii":          json.loads(row["pii_json"]),
        "gatekeeper":   json.loads(row["gatekeeper_json"] or "[]"),
        "ocr_used":     bool(row["ocr_used"]),
        "quality":      row["quality"],
        "created_at":   row["created_at"],
    }


def list_resumes(limit: int = 100, offset: int = 0) -> list[dict]:
    conn = _conn()
    rows = conn.execute(
        "SELECT id, external_id, filename, quality, ocr_used, created_at "
        "FROM resumes ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    return [dict(r) for r in rows]