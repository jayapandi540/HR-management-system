def generate_feedback(resume_data, jd_text, score):
    """Generate candidate feedback based on score."""
    if score >= 75:
        return "Strong match. Proceed to interview."
    elif score >= 60:
        return "Good match. Consider for further review."
    else:
        return "Not a strong match. May require additional skills."