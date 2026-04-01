def classify_resume(resume_data):
    """Return 'fresher', 'experienced', 'executive' based on years."""
    # Simple heuristic
    exp = resume_data.get('experience', [])
    total_years = sum(e.get('duration_years', 0) for e in exp)
    if total_years < 1:
        return 'fresher'
    elif total_years < 5:
        return 'experienced'
    else:
        return 'executive'