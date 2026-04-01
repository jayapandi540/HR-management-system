from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from ..config import SQLITE_PATH

engine = create_engine(f"sqlite:///{SQLITE_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)