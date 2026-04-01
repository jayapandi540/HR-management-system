import duckdb
from pathlib import Path
from ...config import DUCKDB_PATH

def get_connection():
    return duckdb.connect(str(DUCKDB_PATH))

def attach_sqlite():
    conn = get_connection()
    conn.execute(f"ATTACH '{Path(__file__).parent.parent.parent.parent / 'data' / 'resumes.db'}' AS sqlite_db (TYPE SQLITE);")
    return conn