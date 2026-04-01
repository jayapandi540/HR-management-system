def get_parsed_resume(resume_id):
    """Fetch parsed JSON from DB."""
    from ats_system.orm.session import SessionLocal
    from ats_system.orm.models import Resume
    db = SessionLocal()
    resume = db.query(Resume).filter(Resume.id == resume_id).first()
    db.close()
    return resume.masked_json if resume else {}