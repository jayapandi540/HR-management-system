from sqlalchemy import Column, String, Integer, Float, DateTime, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class Resume(Base):
    __tablename__ = "resumes"
    id = Column(String, primary_key=True)
    external_id = Column(String, unique=True)  # user provided
    masked_json = Column(JSON)
    pii_json = Column(JSON)
    status = Column(String, default="new")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Job(Base):
    __tablename__ = "jobs"
    id = Column(String, primary_key=True)
    title = Column(String)
    description = Column(String)
    requirements = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Match(Base):
    __tablename__ = "matches"
    id = Column(String, primary_key=True)
    resume_id = Column(String, ForeignKey("resumes.id"))
    job_id = Column(String, ForeignKey("jobs.id"))
    score = Column(Float)
    ranking = Column(Integer)
    details = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())