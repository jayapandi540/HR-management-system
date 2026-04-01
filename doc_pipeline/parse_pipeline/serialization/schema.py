"""
doc_pipeline/parse_pipeline/serialization/schema.py
====================================================
Section and ResumeDocument dataclasses — the canonical output of parse_pipeline.
Stored as masked_json + pii_json in SQLite resumes.db.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Optional, Any


@dataclass
class Section:
    """One named section of the resume (e.g. EXPERIENCE, EDUCATION)."""
    name:     str
    raw_text: str
    blocks:   list[dict] = field(default_factory=list)   # serialised IngestedBlocks


@dataclass
class WorkEntry:
    company:       Optional[str]  = None
    job_title:     Optional[str]  = None
    start_date:    Optional[str]  = None   # ISO string
    end_date:      Optional[str]  = None
    duration_days: Optional[int]  = None
    description:   Optional[str]  = None
    technologies:  list[str]      = field(default_factory=list)


@dataclass
class EducationEntry:
    institution:     Optional[str]   = None
    degree:          Optional[str]   = None
    field_of_study:  Optional[str]   = None
    graduation_year: Optional[int]   = None
    gpa:             Optional[float] = None


@dataclass
class ProjectEntry:
    name:        Optional[str]  = None
    description: Optional[str]  = None
    technologies:list[str]      = field(default_factory=list)
    url:         Optional[str]  = None


@dataclass
class ContactInfo:
    name:     Optional[str] = None
    email:    Optional[str] = None   # masked in masked_json
    phone:    Optional[str] = None   # masked in masked_json
    linkedin: Optional[str] = None
    location: Optional[str] = None


@dataclass
class ResumeDocument:
    """
    Complete structured output of the parse_pipeline.
    This is what gets stored in resumes.db and consumed by resume_ats.
    """
    resume_id:       str
    contact:         ContactInfo               = field(default_factory=ContactInfo)
    summary:         Optional[str]            = None
    skills:          list[str]                = field(default_factory=list)
    experience:      list[WorkEntry]          = field(default_factory=list)
    education:       list[EducationEntry]     = field(default_factory=list)
    projects:        list[ProjectEntry]       = field(default_factory=list)
    certifications:  list[str]                = field(default_factory=list)
    languages:       list[str]                = field(default_factory=list)
    sections:        dict[str, Section]       = field(default_factory=dict)
    raw_sections:    dict[str, str]           = field(default_factory=dict)
    total_years_exp: float                    = 0.0
    formatting_score:float                    = 0.0
    ocr_used:        bool                     = False
    gatekeeper_hits: list[dict]               = field(default_factory=list)
    metadata:        dict[str, Any]           = field(default_factory=dict)

    def to_dict(self) -> dict:
        import dataclasses
        def _conv(obj: Any) -> Any:
            if isinstance(obj, (date,)):
                return obj.isoformat()
            if dataclasses.is_dataclass(obj):
                return {k: _conv(v) for k, v in dataclasses.asdict(obj).items()}
            if isinstance(obj, (list, tuple)):
                return [_conv(i) for i in obj]
            if isinstance(obj, dict):
                return {k: _conv(v) for k, v in obj.items()}
            return obj
        return _conv(self)