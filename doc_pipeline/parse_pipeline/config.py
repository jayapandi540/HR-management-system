"""doc_pipeline/parse_pipeline/config.py — paths and rejection rule constants."""
from pathlib import Path

BASE_DIR       = Path(__file__).parent.parent   # doc_pipeline/
DATA_DIR       = BASE_DIR / "data"
LOGS_DIR       = BASE_DIR / "logs"
DB_PATH        = DATA_DIR / "resumes.db"
RULES_PATH     = Path(__file__).parent / "rules" / "rejection_rules.json"

LOGS_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)