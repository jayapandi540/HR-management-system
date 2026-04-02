"""
ats_system/ats_backend/orchestration/job_flow.py
=================================================
Orchestration layer — ties Projects 1, 3, and 4 together.

Implements the handle_application() entry point specified in the design doc:

  1. Parse & store resume          → doc_pipeline.parse_pipeline
  2. Run ATS pipeline for this JD  → resume_ats.resume_reviewer.pipeline
  3. Run ranker                    → ats_engine.ats_ranker.pipeline.ranker
  4. Apply band rules & persist    → shared.constants.resolve_band_update
                                     ats_backend.orm.models

This is the ONLY file that imports from all three downstream projects.
"""
from __future__ import annotations

import logging
from typing import Optional

from shared.constants import resolve_band_update

logger = logging.getLogger("ats_backend.job_flow")


# ── Main entry point (from design doc spec) ───────────────────────────────────

def handle_application(
    resume_pdf:   str,
    candidate_id: str,
    job_id:       str,
) -> dict:
    """
    Full pipeline for one candidate+job application.

    Parameters
    ----------
    resume_pdf   : path to uploaded PDF
    candidate_id : external candidate identifier
    job_id       : target job identifier

    Returns
    -------
    dict with band, final_score, ats_score, match_score, reason
    """
    logger.info("[JobFlow] START candidate=%s job=%s", candidate_id, job_id)

    # ── Step 1: Parse & store resume (Project 1) ──────────────────────────────
    from doc_pipeline.parse_pipeline.pipeline import run_pipeline_and_store
    pipeline_result = run_pipeline_and_store(
        pdf_path    = resume_pdf,
        external_id = candidate_id,
    )
    resume_id = pipeline_result.resume_id
    logger.info("[JobFlow] Parsed resume_id=%s status=%s", resume_id, pipeline_result.status)

    if pipeline_result.status == "rejected":
        return {
            "candidate_id": candidate_id,
            "job_id":       job_id,
            "resume_id":    resume_id,
            "band":         "rejected",
            "reason":       "Resume failed gatekeeper rules.",
            "rule_hits":    len(pipeline_result.rule_hits),
        }

    # ── Step 2: ATS pipeline for this JD (Project 3) ─────────────────────────
    from resume_ats.resume_reviewer.pipeline import run_for_job
    ats_result = run_for_job(resume_id=resume_id, job_id=job_id)
    logger.info(
        "[JobFlow] ATS score=%.1f match=%.3f type=%s",
        ats_result.ats_score,
        ats_result.match_score,
        ats_result.resume_type,
    )

    # ── Step 3: Ranking (Project 4) ───────────────────────────────────────────
    from ats_engine.ats_ranker.pipeline.ranker import ATSRanker, RankerInput

    # Retrieve existing band for this candidate+job (for precedence rules)
    existing_band = _get_existing_band(candidate_id, job_id)

    ranker = ATSRanker()
    ranker_input = RankerInput(
        resume_id      = resume_id,
        candidate_id   = candidate_id,
        job_id         = job_id,
        masked_resume  = _load_masked_resume(resume_id),
        ats_score      = ats_result.ats_score,
        match_score    = ats_result.match_score,
        jd_text        = _load_jd_text(job_id),
        portfolio_data = _load_portfolio(candidate_id),
        existing_band  = existing_band,
    )
    ranker_result = ranker.rank_one(ranker_input)

    # ── Step 4: Apply band rules & persist ────────────────────────────────────
    from ats_engine.ats_ranker.pipeline.ranker import update_candidate_bands
    update_candidate_bands(job_id, [ranker_result])

    # Push to Redis priority queue
    from ats_system.ats_backend.storage.redis.queue import push_candidate
    _push_to_queue(ranker_result)

    logger.info(
        "[JobFlow] DONE candidate=%s band=%s (prev=%s) score=%.1f",
        candidate_id,
        ranker_result.band,
        ranker_result.previous_band,
        ranker_result.final_score,
    )

    return {
        "candidate_id": candidate_id,
        "job_id":       job_id,
        "resume_id":    resume_id,
        "band":         ranker_result.band,
        "previous_band":ranker_result.previous_band,
        "band_changed": ranker_result.band_changed,
        "final_score":  ranker_result.final_score,
        "ats_score":    ats_result.ats_score,
        "match_score":  ats_result.match_score,
        "reason":       ranker_result.reason,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_existing_band(candidate_id: str, job_id: str) -> str:
    """Retrieve current band from DB. Returns 'none' if first application."""
    try:
        from ats_system.ats_backend.orm.session import get_sync_session
        from ats_system.ats_backend.orm.models  import CandidateJobBand
        with get_sync_session() as s:
            row = s.query(CandidateJobBand).filter_by(
                candidate_id=candidate_id, job_id=job_id
            ).first()
            return row.band if row else "none"
    except Exception as exc:
        logger.debug("get_existing_band failed: %s", exc)
        return "none"


def _load_masked_resume(resume_id: str) -> dict:
    from doc_pipeline.parse_pipeline.storage.db_client import load_masked
    return load_masked(resume_id) or {}


def _load_jd_text(job_id: str) -> str:
    try:
        from ats_system.ats_backend.orm.session import get_sync_session
        from ats_system.ats_backend.orm.models  import Job
        with get_sync_session() as s:
            job = s.query(Job).filter_by(id=job_id).first()
            return job.description if job else ""
    except Exception:
        return ""


def _load_portfolio(candidate_id: str) -> Optional[dict]:
    """Load portfolio data if available. Returns None if not found."""
    return None   # implement when portfolio ingestion is added


def _push_to_queue(result) -> None:
    """Push ranked candidate to the appropriate Redis queue."""
    try:
        import asyncio
        from ats_system.ats_backend.storage.redis.queue import push_candidate
        asyncio.get_event_loop().run_until_complete(
            push_candidate(
                candidate_id   = result.candidate_id,
                application_id = f"{result.candidate_id}:{result.job_id}",
                ats_total      = result.final_score,
                extra          = {
                    "job_id": result.job_id,
                    "band":   result.band,
                    "grade":  _score_to_grade(result.final_score),
                },
            )
        )
    except Exception as exc:
        logger.warning("Redis push failed: %s", exc)


def _score_to_grade(score: float) -> str:
    if score >= 95: return "A+"
    if score >= 88: return "A"
    if score >= 82: return "B+"
    if score >= 75: return "B"
    if score >= 68: return "C+"
    if score >= 60: return "C"
    if score >= 50: return "D"
    return "F"