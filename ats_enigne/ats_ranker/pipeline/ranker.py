"""
ats_engine/ats_ranker/pipeline/ranker.py
=========================================
Project 4 — Ranking & Band Assignment.

For each candidate in a JD queue (from Redis/DB):
  1. Normalize skills         (core/skill_normalizer.py)
  2. Classify experience      (core/experience_classifier.py)
  3. Analyze portfolio        (core/portfolio_analyzer.py)
  4. Compute final score      (core/scorer.py)
  5. Assign band              (core/scoring_config.py  →  assign_band())
  6. Apply band update rules  (shared/constants.py     →  resolve_band_update())
  7. Persist to ATS DB        (ats_backend/orm/models.py via ats_backend)

Band update precedence (from spec):
  New GOLD   → always upgrade
  New SILVER → upgrade bronze/rejected; keep existing gold or better silver
  New BRONZE → never downgrade gold/silver
  New REJECTED → only overwrite when no gold/silver history
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from shared.constants import CandidateBand, resolve_band_update
from ats_engine.ats_ranker.core.scoring_config import assign_band

logger = logging.getLogger("ats_ranker.ranker")


# ── Output dataclasses ────────────────────────────────────────────────────────

@dataclass
class RankerInput:
    """Everything the ranker needs for one candidate+job."""
    resume_id:       str
    candidate_id:    str
    job_id:          str
    masked_resume:   dict                  # from doc_pipeline SQLite masked_json
    ats_score:       float                 # from resume_reviewer (0–100)
    match_score:     float                 # from jd_matcher (0–1)
    jd_text:         str   = ""
    portfolio_data:  Optional[dict] = None
    existing_band:   str   = "none"        # current band in DB for this candidate+job


@dataclass
class RankerResult:
    resume_id:     str
    candidate_id:  str
    job_id:        str
    final_score:   float
    ats_score:     float
    match_score:   float
    band:          str              # gold | silver | bronze | rejected
    previous_band: str
    band_changed:  bool
    skills_normalized: dict[str, float] = field(default_factory=dict)
    experience_level:  str               = "mid_level"
    portfolio_summary: Optional[dict]    = None
    reason:            str               = ""
    semantic_tags:     list[str]         = field(default_factory=list)


# ── Ranker ────────────────────────────────────────────────────────────────────

class ATSRanker:
    """
    Ranking engine for Project 4.

    Parameters
    ----------
    use_slm_reasons : bool
        If True, calls the SLM client to generate human-readable reason strings.
        If False, uses rule-based reason generation (no API cost).
    """

    def __init__(self, use_slm_reasons: bool = False) -> None:
        self._use_slm = use_slm_reasons

    # ── Public API ────────────────────────────────────────────────────────────

    def rank_one(self, inp: RankerInput) -> RankerResult:
        """
        Run the full ranking pipeline for one candidate+job pair.

        Parameters
        ----------
        inp : RankerInput

        Returns
        -------
        RankerResult — includes new band and whether it changed
        """
        from ats_engine.ats_ranker.core.skill_normalizer import normalize_skills
        from ats_engine.ats_ranker.core.experience_classifier import classify_experience
        from ats_engine.ats_ranker.core.portfolio_analyzer import analyze_portfolio
        from ats_engine.ats_ranker.core.scorer import compute_final_score
        from ats_engine.ats_ranker.nlp.semantic_tagger import SemanticTagger

        resume = inp.masked_resume

        # ── Step 1: Normalize skills ──────────────────────────────────────────
        raw_skills = [s.get("name","") for s in resume.get("skills", [])]
        skills_norm = normalize_skills(raw_skills, seniority=_rough_level(resume))

        # ── Step 2: Classify experience ───────────────────────────────────────
        exp_profile = classify_experience(
            years     = resume.get("total_years_exp", 0.0),
            work_text = " ".join(
                e.get("description", "") or "" for e in resume.get("experience", [])
            ),
            target_domain = _infer_domain(inp.jd_text),
        )

        # ── Step 3: Portfolio analysis ────────────────────────────────────────
        portfolio_summary = None
        if inp.portfolio_data:
            portfolio_summary = analyze_portfolio(inp.portfolio_data, inp.jd_text)

        # ── Step 4: Semantic tags ─────────────────────────────────────────────
        tagger = SemanticTagger()
        work_text = " ".join(
            (e.get("description") or "") + " " + (e.get("job_title") or "")
            for e in resume.get("experience", [])
        )
        semantic_tags = tagger.tag(
            text          = work_text,
            existing_tags = resume.get("semantic_tags", []),
        )

        # ── Step 5: Final score ───────────────────────────────────────────────
        final_score = compute_final_score(
            resume         = resume,
            skills_norm    = skills_norm,
            exp_profile    = exp_profile,
            portfolio      = portfolio_summary,
            ats_score      = inp.ats_score,
            match_score    = inp.match_score,
        )

        # ── Step 6: Band assignment ───────────────────────────────────────────
        raw_band  = assign_band(final_score, inp.ats_score, inp.match_score)
        new_band  = resolve_band_update(inp.existing_band, raw_band)

        # ── Step 7: Reason ────────────────────────────────────────────────────
        reason = self._generate_reason(
            resume     = resume,
            final_score= final_score,
            band       = new_band,
            skills_norm= skills_norm,
            semantic   = semantic_tags,
        )

        result = RankerResult(
            resume_id          = inp.resume_id,
            candidate_id       = inp.candidate_id,
            job_id             = inp.job_id,
            final_score        = round(final_score, 2),
            ats_score          = inp.ats_score,
            match_score        = inp.match_score,
            band               = new_band,
            previous_band      = inp.existing_band,
            band_changed       = new_band != inp.existing_band,
            skills_normalized  = {k: round(v, 1) for k, v in skills_norm.items()},
            experience_level   = exp_profile.level if hasattr(exp_profile, "level") else "mid_level",
            portfolio_summary  = portfolio_summary,
            reason             = reason,
            semantic_tags      = semantic_tags,
        )

        logger.info(
            "[Ranker] candidate=%s job=%s score=%.1f band=%s (was %s, changed=%s)",
            inp.candidate_id, inp.job_id, final_score,
            new_band, inp.existing_band, result.band_changed,
        )
        return result

    def rank_for_job(self, job_id: str, candidate_inputs: list[RankerInput]) -> list[RankerResult]:
        """
        Rank all candidates for one job. Returns list sorted by final_score desc.
        Used by ats_backend/orchestration/job_flow.py.
        """
        results = [self.rank_one(inp) for inp in candidate_inputs]
        results.sort(key=lambda r: r.final_score, reverse=True)
        return results

    # ── Reason generation ─────────────────────────────────────────────────────

    def _generate_reason(
        self,
        resume:      dict,
        final_score: float,
        band:        str,
        skills_norm: dict[str, float],
        semantic:    list[str],
    ) -> str:
        """
        Rule-based reason string (no SLM cost).
        SLM path handled by slm_client.py if use_slm_reasons=True.
        """
        if self._use_slm:
            try:
                from doc_pipeline.parse_pipeline.slm.slm_client import SLMClient
                return SLMClient().generate_reason(resume, final_score, band, skills_norm)
            except Exception as exc:
                logger.warning("SLM reason failed: %s — using rule fallback.", exc)

        top_skills = list(skills_norm.keys())[:3]
        tags       = semantic[:2]
        skill_str  = ", ".join(top_skills) if top_skills else "core skills"
        tag_str    = " and ".join(tags) if tags else ""

        if band == CandidateBand.GOLD.value:
            return (
                f"Gold-band candidate (score {final_score:.0f}/100). "
                f"Strong alignment in {skill_str}"
                + (f" with domain expertise in {tag_str}." if tag_str else ".")
            )
        if band == CandidateBand.SILVER.value:
            return (
                f"Silver-band candidate (score {final_score:.0f}/100). "
                f"Good {skill_str} coverage; re-ranked on next application."
            )
        if band == CandidateBand.BRONZE.value:
            return (
                f"Bronze-band candidate (score {final_score:.0f}/100). "
                f"Partial match — kept as low-priority."
            )
        return (
            f"Rejected (score {final_score:.0f}/100). "
            f"Insufficient match against JD requirements."
        )


# ── Band persistence (called by orchestration) ────────────────────────────────

def update_candidate_bands(job_id: str, results: list[RankerResult]) -> None:
    """
    Persist band results for all candidates to the ATS DB.
    Applies the band update precedence rules via resolve_band_update().

    Called by ats_backend/orchestration/job_flow.py after rank_for_job().
    """
    try:
        from ats_system.ats_backend.orm.session import get_sync_session
        from ats_system.ats_backend.orm.models  import CandidateJobBand

        with get_sync_session() as session:
            for r in results:
                row = session.query(CandidateJobBand).filter_by(
                    candidate_id = r.candidate_id,
                    job_id       = r.job_id,
                ).first()

                if row is None:
                    row = CandidateJobBand(
                        candidate_id = r.candidate_id,
                        job_id       = r.job_id,
                    )
                    session.add(row)

                row.band       = r.band
                row.final_score= r.final_score
                row.ats_score  = r.ats_score
                row.match_score= r.match_score

            session.commit()
        logger.info("Band update persisted for %d candidates, job=%s.", len(results), job_id)

    except Exception as exc:
        logger.error("Band persistence failed: %s", exc)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rough_level(resume: dict) -> str:
    yrs = resume.get("total_years_exp", 0.0)
    if yrs <= 2:   return "fresh"
    if yrs <= 6:   return "mid"
    if yrs <= 10:  return "senior"
    return "executive"


def _infer_domain(jd_text: str) -> str:
    jd_lower = jd_text.lower()
    if any(kw in jd_lower for kw in ["software","engineer","developer","backend","frontend"]):
        return "tech"
    if any(kw in jd_lower for kw in ["design","ux","ui","figma"]):
        return "design"
    if any(kw in jd_lower for kw in ["data","ml","machine learning","etl","pipeline"]):
        return "data"
    if any(kw in jd_lower for kw in ["product","roadmap","agile","scrum"]):
        return "product"
    if any(kw in jd_lower for kw in ["sales","crm","revenue","quota"]):
        return "sales"
    return "tech"