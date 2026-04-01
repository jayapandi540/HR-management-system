"# HR-management-system" 

# hr_management_system/README.md

## 🚀 AI-Assisted ATS

**One-line**: Parses resumes (OCR fallback), matches JDs, scores/ranks explainably, recruiter dashboard + Redis scaling.

[

## Features
- PDF ingestion + OCR (PyMuPDF/PaddleOCR/spaCy PII mask)
- JD matching (TF-IDF/cosine), ATS scoring/ranking
- Redis queues, DuckDB analytics, Chroma vectors
- FastAPI + React UI (filters/shortlists/feedback)
- Admin config, audits, returning-candidate detect [perplexity](https://www.perplexity.ai/search/baa8d10c-ce0c-402f-8d52-a32547da9b83)

## 📁 Structure
```
hr_management_system/
├── api/          # FastAPI: /upload /match /rank /admin
├── pipeline/     # Ingest→OCR→parse→PII→storage
├── services/     # Classifier/matcher/scorer/ranker/feedback
├── storage/      # SQLite/Redis/DuckDB/Chroma
├── analytics/    # Funnel queries
├── ui/           # React dashboard
├── tests/
├── docker-compose.yml
└── pyproject.toml
```
Monorepo evolves your doc_pipeline/resume_ats/ats_ranker/ats_system. [perplexity](https://www.perplexity.ai/search/6c83f498-a487-4d07-a9aa-757229141f17)

## Quickstart
```bash
git clone <repo> && cd hr_management_system
pip install -e .  # or docker-compose up
curl -F "resume=@test.pdf" -F "jd=@job.txt" http://localhost:8000/api/match
```

## 4-Week Sprints
| Week | Focus | Deliverable |
|------|--------|-------------|
| 1 | Parsing pipeline | PDF→JSON DB save |
| 2 | Matching/scoring APIs | End-to-end score |
| 3 | Queues/ranking/feedback | Shortlist + UI |
| 4 | Analytics/tests/Docker | v1 release [recruitbpm](https://recruitbpm.com/blog/resume-parser-recruiters) |

## Tech
- **Backend**: FastAPI/Pydantic/SQLAlchemy
- **ML**: scikit-learn/XGBoost
- **Infra**: Redis/DuckDB/Chroma/Prometheus [linkedin](https://www.linkedin.com/posts/arvami-solutionz_the-queue-mode-architecture-activity-7430249828397293568-vGDz)

## Testing
- Unit: parsers/scorers
- Integration: queue flows
- Model: F1/rank eval on labeled data [47billion](https://47billion.com/blog/rethinking-resume-scoring-how-llms-are-transforming-ats-for-the-ai-generation/)


***

Copy-paste this compact Markdown into `README.md`—fits GitHub render, SEO-optimized, prior specs integrated. Want `docker-compose.yml` next? [perplexity](https://www.perplexity.ai/search/f7677702-b5d2-43b5-9179-e682c2663bdd)