def rank_candidates(job_id):
    """Retrieve candidates from Redis queue, compute final score, rank."""
    from ats_system.storage.redis.queue import redis_client
    from ats_system.orm.session import SessionLocal
    from ats_system.orm.models import Match
    import json

    queue_key = f"job:{job_id}:candidates"
    candidates = redis_client.zrevrange(queue_key, 0, -1, withscores=True)
    # candidates is list of (value, score)
    ranked = []
    for value, ats_score in candidates:
        resume_id, _ = value.split(':')
        # Get resume data from DB
        db = SessionLocal()
        resume = db.query(Resume).filter(Resume.id == resume_id).first()
        if resume:
            # Compute combined score (just use ats_score for now)
            combined = ats_score  # in real, call scorer
            ranked.append({"resume_id": resume_id, "score": combined, "details": {}})
        db.close()
    # Sort by score descending
    ranked.sort(key=lambda x: x['score'], reverse=True)
    return ranked