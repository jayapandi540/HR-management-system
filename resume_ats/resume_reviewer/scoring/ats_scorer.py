def score_resume(resume_data, jd_text, match_result):
    """Combine match similarity, experience, skills, etc."""
    similarity = match_result.get("similarity", 0)
    # Simple weighted score
    base_score = similarity * 100
    # Bonus for experience
    exp_years = sum(e.get('duration_years', 0) for e in resume_data.get('experience', []))
    if exp_years > 5:
        base_score += 5
    elif exp_years > 2:
        base_score += 2
    return min(100, base_score)