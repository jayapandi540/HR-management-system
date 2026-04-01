from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .middleware import add_middleware
from .routes import resumes, jobs, match, rank, admin
from ats_system.telemetry.logging import setup_logging

app = FastAPI(title="HR Management System ATS", version="0.1.0")
add_middleware(app)

app.include_router(resumes.router, prefix="/resumes", tags=["resumes"])
app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
app.include_router(match.router, prefix="/match", tags=["match"])
app.include_router(rank.router, prefix="/rank", tags=["rank"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])

@app.on_event("startup")
def startup():
    setup_logging()
    # Initialize DB, etc.
    from ats_system.orm.session import engine
    from ats_system.orm.models import Base
    Base.metadata.create_all(bind=engine)
    from doc_pipeline.storage.db_client import init_db
    init_db()