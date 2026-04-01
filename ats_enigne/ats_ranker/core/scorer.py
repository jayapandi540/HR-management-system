def combined_score(resume_data, jd_text, ats_score):
    """Combine ATS score with portfolio score."""
    portfolio_score = analyze_portfolio(resume_data)
    # Weighted average
    final = 0.6 * ats_score + 0.4 * portfolio_score
    return final

def analyze_portfolio(resume_data):
    """Simple placeholder."""
    # Check for github links, projects, etc.
    if resume_data.get('profile_links'):
        return 80
    return 60