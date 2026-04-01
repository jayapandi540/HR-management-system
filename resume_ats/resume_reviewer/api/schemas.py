from pydantic import BaseModel
from typing import List, Optional

class ResumeUploadResponse(BaseModel):
    id: str
    status: str

class JobCreate(BaseModel):
    title: str
    description: str
    requirements: Optional[dict] = None

class MatchRequest(BaseModel):
    resume_id: str
    job_id: str

class MatchResponse(BaseModel):
    score: float
    details: dict

class RankRequest(BaseModel):
    job_id: str
    limit: int = 10