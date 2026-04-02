"""
doc_pipeline/parse_pipeline/serialization/schema.py
====================================================
Core data models for parsed resume output.

Section        — one labelled section (EXPERIENCE, EDUCATION, SKILLS, …)
ResumeDocument — full structured output of parse_pipeline/pipeline.py
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class SkillEntry:
    name:       str
    score:      float = 0.0         # normalised 0–10
    source:     str   = "inferred"  # "label" | "fraction" | "percent" | "visual" | "inferred"


@dataclass
class WorkEntry:
    company:       Optional[str] = None
    job_title:     Optional[str] = None
    start_date:    Optional[date] = None
    end_date:      Optional[date] = None
    duration_days: Optional[int]  = None
    description:   Optional[str] = None
    technologies:  list[str] = field(default_factory=list)


@dataclass
class EducationEntry:
    institution:     Optional[str]   = None
    degree:          Optional[str]   = None
    field_of_study:  Optional[str]   = None
    graduation_year: Optional[int]   = None
    gpa:             Optional[float] = None


@dataclass
class CertificationEntry:
    name:        str
    issuer:      Optional[str] = None
    issued_date: Optional[date] = None
    expiry_date: Optional[date] = None


@dataclass
class ProjectEntry:
    name:         str
    description:  Optional[str]  = None
    technologies: list[str]      = field(default_factory=list)
    url:          Optional[str]  = None


@dataclass
class Section:
    """
    One labelled section of the resume with its raw and cleaned text.
    heading matches the section name detected by section_parser.py.
    """
    heading:      str            # e.g. "EXPERIENCE", "EDUCATION", "SKILLS"
    raw_text:     str
    cleaned_text: str
    page_nums:    list[int] = field(default_factory=list)
    rejected:     bool      = False
    reject_reason:Optional[str] = None


@dataclass
class ContactInfo:
    name:     Optional[str] = None
    email:    Optional[str] = None
    phone:    Optional[str] = None
    linkedin: Optional[str] = None
    github:   Optional[str] = None
    location: Optional[str] = None
    website:  Optional[str] = None


@dataclass
class ResumeDocument:
    """
    Full structured output of the parse pipeline.
    This is what gets stored in SQLite (as masked_json / pii_json)
    and consumed by Project 2 / 3 / 4.
    """
    # Identity
    resume_id:      str
    external_id:    Optional[str]  = None

    # Contact (PII — stored in pii_json only, masked in masked_json)
    contact:        ContactInfo    = field(default_factory=ContactInfo)

    # Content
    summary:        Optional[str]  = None
    skills:         list[SkillEntry]       = field(default_factory=list)
    experience:     list[WorkEntry]        = field(default_factory=list)
    education:      list[EducationEntry]   = field(default_factory=list)
    certifications: list[CertificationEntry] = field(default_factory=list)
    projects:       list[ProjectEntry]     = field(default_factory=list)
    languages:      list[str]              = field(default_factory=list)
    profile_links:  list[str]              = field(default_factory=list)

    # Sections (raw + cleaned, for downstream reference)
    sections:       list[Section]  = field(default_factory=list)

    # Metadata
    total_years_exp: float         = 0.0
    formatting_score:float         = 0.0
    ocr_used:        bool          = False
    page_count:      int           = 0
    raw_text:        str           = ""

    def to_masked_dict(self) -> dict:
        """Return dict with PII fields replaced by placeholders."""
        import dataclasses, json
        d = dataclasses.asdict(self)
        if d.get("contact"):
            d["contact"] = {
                "name":     "[NAME]"     if d["contact"].get("name")     else None,
                "email":    "[EMAIL]"    if d["contact"].get("email")    else None,
                "phone":    "[PHONE]"    if d["contact"].get("phone")    else None,
                "linkedin": "[LINKEDIN]" if d["contact"].get("linkedin") else None,
                "github":   d["contact"].get("github"),   # not PII
                "location": d["contact"].get("location"), # city-level OK
                "website":  d["contact"].get("website"),
            }
        return d

    def to_pii_dict(self) -> dict:
        """Return full dict including raw PII (restricted access)."""
        import dataclasses
        return dataclasses.asdict(self)