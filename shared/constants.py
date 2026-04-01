"""
shared/constants.py
===================
Shared enums, band names, and status constants used across all 4 projects.
Single source of truth — never redefine in individual projects.
"""
from __future__ import annotations
from enum import Enum


class Band(str, Enum):
    GOLD     = "gold"
    SILVER   = "silver"
    BRONZE   = "bronze"
    REJECTED = "rejected"
    PENDING  = "pending"


class ResumeType(str, Enum):
    SOFTWARE_ENGINEER = "software_engineer"
    DATA_ENGINEER     = "data_engineer"
    DESIGNER          = "designer"
    PRODUCT_MANAGER   = "product_manager"
    SALES             = "sales"
    MARKETING         = "marketing"
    HR                = "hr"
    FINANCE           = "finance"
    UNKNOWN           = "unknown"


class PageQuality(str, Enum):
    NORMAL     = "normal"
    PIXEL_ONLY = "pixel_only"
    GARBLED    = "garbled"
    LOW_OCR    = "low_ocr"


class GatekeeperAction(str, Enum):
    PASS    = "pass"
    IGNORE  = "ignore"
    REJECT  = "reject"
    FLAG    = "flag"
    DEDUP   = "deduplicate"


class ApplicationStatus(str, Enum):
    PENDING     = "pending"
    PARSING     = "parsing"
    PARSED      = "parsed"
    SCORED      = "scored"
    RANKED      = "ranked"
    SHORTLISTED = "shortlisted"
    REJECTED    = "rejected"
    ON_HOLD     = "on_hold"


class SectionName(str, Enum):
    CONTACT        = "contact"
    SUMMARY        = "summary"
    EXPERIENCE     = "experience"
    EDUCATION      = "education"
    SKILLS         = "skills"
    PROJECTS       = "projects"
    CERTIFICATIONS = "certifications"
    LANGUAGES      = "languages"
    AWARDS         = "awards"
    REFERENCES     = "references"
    LINKS          = "links"
    UNKNOWN        = "unknown"


# ── Band upgrade matrix ───────────────────────────────────────────────────────
# (current_band, new_band) → resulting_band
# Gold is sticky — never downgraded. Silver protected from Bronze/Rejected.

BAND_UPDATE_RULES: dict[tuple[str, str], str] = {
    (Band.GOLD,     Band.GOLD):     Band.GOLD,
    (Band.SILVER,   Band.GOLD):     Band.GOLD,
    (Band.BRONZE,   Band.GOLD):     Band.GOLD,
    (Band.REJECTED, Band.GOLD):     Band.GOLD,
    (Band.PENDING,  Band.GOLD):     Band.GOLD,
    (Band.GOLD,     Band.SILVER):   Band.GOLD,    # gold protected
    (Band.SILVER,   Band.SILVER):   Band.SILVER,
    (Band.BRONZE,   Band.SILVER):   Band.SILVER,
    (Band.REJECTED, Band.SILVER):   Band.SILVER,
    (Band.PENDING,  Band.SILVER):   Band.SILVER,
    (Band.GOLD,     Band.BRONZE):   Band.GOLD,    # gold protected
    (Band.SILVER,   Band.BRONZE):   Band.SILVER,  # silver protected
    (Band.BRONZE,   Band.BRONZE):   Band.BRONZE,
    (Band.REJECTED, Band.BRONZE):   Band.BRONZE,
    (Band.PENDING,  Band.BRONZE):   Band.BRONZE,
    (Band.GOLD,     Band.REJECTED): Band.GOLD,
    (Band.SILVER,   Band.REJECTED): Band.SILVER,
    (Band.BRONZE,   Band.REJECTED): Band.BRONZE,
    (Band.REJECTED, Band.REJECTED): Band.REJECTED,
    (Band.PENDING,  Band.REJECTED): Band.REJECTED,
}


def resolve_band(current: str, new_band: str) -> str:
    """Apply the band update matrix — gold and silver are sticky."""
    key = (Band(current), Band(new_band))
    return BAND_UPDATE_RULES.get(key, new_band)


QUEUE_CANDIDATES = "ats:queue:candidates"
QUEUE_REPORTS    = "ats:queue:reports"
QUEUE_REVIEW     = "ats:queue:review"