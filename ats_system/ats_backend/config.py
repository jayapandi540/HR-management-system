import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SQLITE_PATH = DATA_DIR / "resumes.db"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DUCKDB_PATH = DATA_DIR / "analytics.duckdb"