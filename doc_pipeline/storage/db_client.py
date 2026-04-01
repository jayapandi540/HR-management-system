import sqlite3
import json
from pathlib import Path
from ..config import DB_PATH

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS resumes (
            id TEXT PRIMARY KEY,
            masked_json TEXT,
            pii_json TEXT,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.close()

def store_resume(resume_id: str, masked_json: dict, pii_json: dict):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO resumes (id, masked_json, pii_json, status) VALUES (?, ?, ?, ?)",
        (resume_id, json.dumps(masked_json), json.dumps(pii_json), 'completed')
    )
    conn.commit()
    conn.close()