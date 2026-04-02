"""
shared/constants.py
===================
Single source of truth for all shared enums, band names, pipeline statuses,
and constants used across all four projects.

Import pattern:
    from shared.constants import CandidateBand, PipelineStatus, ResumeType
"""
from __future__ import annotations
from enum import Enum


class CandidateBand(str, Enum):
    GOLD     = "gold"
    SILVER   = "silver"
    BRONZE   = "bronze"
    REJECTED = "rejected"


class PipelineStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETE  = "complete"
    FAILED    = "failed"
    FLAGGED   = "flagged"


class ResumeType(str, Enum):
    FRESH_GRAD    = "fresh_grad"
    MID_LEVEL     = "mid_level"
    SENIOR        = "senior"
    EXECUTIVE     = "executive"
    CAREER_CHANGE = "career_change"


class PageQuality(str, Enum):
    NORMAL     = "normal"
    PIXEL_ONLY = "pixel_only"
    GARBLED    = "garbled"
    REJECTED   = "rejected"


class RuleCategory(str, Enum):
    LAYOUT  = "layout"
    VISUAL  = "visual"
    CONTENT = "content"
    SOURCE  = "source"


class RuleAction(str, Enum):
    IGNORE = "ignored"
    REJECT = "rejected"
    FLAG   = "flagged"
    CLEAN  = "clean"
    DEDUP  = "deduplicate"


# Redis queue names
REDIS_QUEUE_CANDIDATES = "slam:queue:candidates"
REDIS_QUEUE_REPORTS    = "slam:queue:reports"
REDIS_QUEUE_GOLD       = "queue:gold"
REDIS_QUEUE_SILVER     = "queue:silver"
REDIS_QUEUE_BRONZE     = "queue:bronze"
REDIS_QUEUE_REVIEW     = "queue:review"

# Band update precedence matrix
# Row = existing band, Col = new band → resulting band
BAND_UPDATE_MATRIX: dict[str, dict[str, str]] = {
    "gold":     {"gold": "gold",   "silver": "gold",   "bronze": "gold",   "rejected": "gold"},
    "silver":   {"gold": "gold",   "silver": "silver", "bronze": "silver", "rejected": "silver"},
    "bronze":   {"gold": "gold",   "silver": "silver", "bronze": "bronze", "rejected": "bronze"},
    "rejected": {"gold": "gold",   "silver": "silver", "bronze": "bronze", "rejected": "rejected"},
    "none":     {"gold": "gold",   "silver": "silver", "bronze": "bronze", "rejected": "rejected"},
}


def resolve_band_update(existing: str, new_band: str) -> str:
    """Apply band precedence rules. Gold never downgrades. Silver protects bronze."""
    row = BAND_UPDATE_MATRIX.get(existing, BAND_UPDATE_MATRIX["none"])
    return row.get(new_band, existing)