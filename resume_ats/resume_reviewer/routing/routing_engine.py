from ats_system.storage.redis.queue import push_job

def route_candidate(resume_id, job_id, score):
    """Push candidate to job-specific queue with score as priority."""
    queue_key = f"job:{job_id}:candidates"
    push_job(queue_key, f"{resume_id}:{job_id}", priority=score)