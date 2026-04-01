"""Main ATS pipeline: parse, classify, match, score, route, feedback."""

from .ingest.ocr_parser import get_parsed_resume
from .classifier.type_classifier import classify_resume
from .matching.jd_matcher import match_resume_to_jd
from .scoring.ats_scorer import score_resume
from .routing.routing_engine import route_candidate
from .feedback.feedback_generator import generate_feedback
from .agent.ats_agent import maybe_adjust_thresholds
from ats_system.orm.session import SessionLocal
from ats_system.orm.models import Resume, Job, Match
import uuid

def run_ats_pipeline(resume_id: str, job_id: str):
    """Orchestrate the ATS flow for a single resume against a job."""
    db = SessionLocal()
    try:
        # 1. Retrieve resume and job
        resume = db.query(Resume).filter(Resume.id == resume_id).first()
        job = db.query(Job).filter(Job.id == job_id).first()
        if not resume or not job:
            return

        # 2. Get parsed data (already stored in resume.masked_json)
        resume_data = resume.masked_json

        # 3. Classify
        resume_type = classify_resume(resume_data)

        # 4. Match
        match_result = match_resume_to_jd(resume_data, job.description)

        # 5. Score
        ats_score = score_resume(resume_data, job.description, match_result)

        # 6. Route (add to Redis queue for ranking)
        route_candidate(resume_id, job_id, ats_score)

        # 7. Generate feedback (optional)
        feedback = generate_feedback(resume_data, job.description, ats_score)

        # 8. Agent (maybe adjust thresholds based on feedback)
        maybe_adjust_thresholds()

        # 9. Store match
        match = Match(
            id=str(uuid.uuid4()),
            resume_id=resume_id,
            job_id=job_id,
            score=ats_score,
            details={"match": match_result, "feedback": feedback, "type": resume_type}
        )
        db.add(match)
        db.commit()
    finally:
        db.close()