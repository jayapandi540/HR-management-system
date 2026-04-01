from pydantic import BaseModel
from typing import List, Optional

class ResumeDocument(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    skills: List[str] = []
    experience: List[dict] = []
    education: List[dict] = []
    certificates: List[str] = []
    projects: List[dict] = []
    sections: dict = {}
    title: Optional[str] = None
    profile_links: List[str] = []