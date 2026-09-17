# ShortlistOS — Real ATS Foundation

This is the real, working foundation for the full ATS product (the one previously
prototyped in a static HTML/JS mockup) — companies, job requisitions, candidate pipeline,
recruiter screening, client portal, analytics. Everything here is a real database, real
API, real persisted state — no localStorage, no mock data.

```
backend/     FastAPI + PostgreSQL + Celery/Redis
frontend/    React + Vite + TypeScript, custom CSS
```

## What's real and working now

- **Companies** — onboard client companies, create job requisitions under them
- **Job requisitions** — full real fields: budget range, locations, experience band,
  max notice period, required skills
- **Candidates directory** — one record per person, independent of any role; add
  manually or via bulk resume upload
- **Candidate pipeline (per job)** — the core screening workflow: bulk-upload resumes for
  a role (creates "Pending Screening" stubs), or search-and-assess an existing candidate;
  full screening-call form (CTC, notice period, skill/experience/communication ratings,
  free-text notes, red flags); score computed and shown live
- **Send to client** — multi-select shortlisted candidates, mark as sent
- **Analytics** — hiring funnel, per-role breakdown

## What's a deliberate placeholder (real AI work comes next, in detail)

The **AI resume-JD matching score** shown throughout the pipeline is currently computed by
`backend/app/services/scoring/placeholder_engine.py` — a direct port of the original
prototype's mock logic (keyword overlap + an experience-band formula). This is clearly
commented in the code as a stand-in.

The **real AI pipeline already exists in this codebase** and is fully separate, untouched,
and ready to be wired in:
- `services/llm/` — GPT-5 structured extraction + scoring, with real prompts
- `services/embeddings/` — provider-agnostic embedding generation
- `services/search/hybrid_search.py` — pgvector + keyword hybrid search
- `workers/tasks_ingestion.py` / `tasks_matching.py` — the Celery pipeline that runs all of
  the above

When the AI work happens (chunking/parsing refinements, real scoring wired into the
pipeline), only `placeholder_engine.py`'s `ai_match_score()` function needs to be replaced
with a real lookup into `match_results` — nothing else in the assessment/pipeline code
needs to change, because the interface (score + matched/missing skills) is already the
same shape.

## Data model

| Table | Purpose |
|---|---|
| companies | Client companies the agency recruits for |
| job_postings | Requisitions, now belonging to a company (not a user) |
| candidates | One record per person, resume-linked, job-independent |
| assessments | **New** — one screening record per (candidate, job) pair; this is the core new entity, matching the prototype's Candidate/Assessment split |
| candidate_profiles / candidate_embeddings / match_results | The existing real AI pipeline's tables — untouched, not yet wired into the ATS flow above |
| users | Agency staff (recruiters), JWT auth |

## Setup

Same as before — see the setup history in this conversation, or work through:
1. `backend/README.md` — Python venv, PostgreSQL + pgvector, Redis, `.env`, migrations
2. Run migrations: since models changed significantly (new Company/Assessment tables,
   extended JobPosting/Candidate), you'll need a fresh `alembic revision --autogenerate`
   — review the generated file carefully before applying, same as always. If you have
   existing data from before this change, expect the autogenerate diff to be large (new
   tables + renamed/changed columns on job_postings and candidates).
3. `frontend/` — `npm install && npm run dev`

## Honest verification status

Backend: all 62 Python files pass `py_compile` (syntax-checked, not run against a live
DB in this environment — no network/DB access here). Frontend: written and manually
reviewed for consistent types/imports against the backend's schemas, but **not compiled**
in this environment (no npm registry access here) — `npm install` on your machine is the
real first test, same situation as the previous frontend delivery.
