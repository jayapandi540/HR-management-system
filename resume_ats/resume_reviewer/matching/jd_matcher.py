from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

def match_resume_to_jd(resume_data, jd_text):
    """Return similarity score and skill gaps."""
    resume_text = " ".join([
        " ".join(resume_data.get('skills', [])),
        " ".join([e.get('title', '') for e in resume_data.get('experience', [])])
    ])
    # Compute cosine similarity
    vectorizer = TfidfVectorizer()
    corpus = [resume_text, jd_text]
    tfidf = vectorizer.fit_transform(corpus)
    similarity = cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0]
    return {"similarity": similarity}