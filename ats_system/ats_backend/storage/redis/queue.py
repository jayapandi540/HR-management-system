import redis
import json
from ...config import REDIS_URL

redis_client = redis.from_url(REDIS_URL, decode_responses=True)

def push_job(job_id: str, priority: float = 1.0):
    """Push job to queue with priority (higher = first)."""
    redis_client.zadd("job_queue", {job_id: priority})

def pop_job():
    """Pop highest priority job."""
    job = redis_client.zpopmax("job_queue")
    if job:
        return job[0][0]
    return None