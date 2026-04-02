"""
ats_engine/ats_ranker/core/scoring_config.py
=============================================
Central thresholds for Gold / Silver / Bronze band assignment.

All three conditions must be met simultaneously for a band to be awarded.
If none of the bands qualifies → "rejected".
"""
from __future__ import annotations
from shared.constants import CandidateBand

BANDS: dict[str, dict[str, float]] = {
    "gold":   {"min_score": 85.0, "min_ats_score": 75.0, "min_match": 0.75},
    "silver": {"min_score": 70.0, "min_ats_score": 60.0, "min_match": 0.60},
    "bronze": {"min_score": 55.0, "min_ats_score": 50.0, "min_match": 0.50},
}

# Score weights for the final ranking score
SCORE_WEIGHTS = {
    "skills":      0.35,
    "experience":  0.25,
    "education":   0.15,
    "keywords":    0.15,
    "formatting":  0.10,
}

# Portfolio weights in combined score
COMBINED_WEIGHTS = {
    "resume":    0.70,
    "relevance": 0.20,
    "activity":  0.10,
}

# Silver candidate re-rank rules
SILVER_RERANK = {
    "upgrade_on_higher_score": True,   # re-parsed resume with better score → upgrade
    "downgrade_on_lower_score": False,  # never downgrade silver
    "audit_retain_days": 90,            # keep old records for 90 days
}

# Cooling-off period for "rejected" status before re-consideration (days)
REJECTED_COOLING_DAYS = 180


def assign_band(
    final_score: float,
    ats_score:   float,
    match_score: float,
) -> str:
    """
    Assign a band based on the three-condition rule.

    Parameters
    ----------
    final_score : 0–100   final ranking score from ats_ranker
    ats_score   : 0–100   ATS score from resume_reviewer
    match_score : 0–1     JD cosine similarity from jd_matcher

    Returns
    -------
    "gold" | "silver" | "bronze" | "rejected"
    """
    for band_name in ("gold", "silver", "bronze"):
        thresholds = BANDS[band_name]
        if (
            final_score >= thresholds["min_score"]
            and ats_score   >= thresholds["min_ats_score"]
            and match_score >= thresholds["min_match"]
        ):
            return band_name
    return CandidateBand.REJECTED.value