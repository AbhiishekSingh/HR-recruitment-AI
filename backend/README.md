# AI Resume Screening System — Backend Skeleton

Matches the architecture in the project doc: FastAPI + PostgreSQL/pgvector + Celery/Redis,
deployed on a single Hostinger VPS via Docker Compose, no cloud services, no CI/CD.

## Structure

```
app/
  main.py                    FastAPI entrypoint
  config.py                  Settings (reads .env)
  db/                        SQLAlchemy engine/session + declarative base
  models/                    ORM models (candidates, profiles, embeddings, jobs, matches, users)
  schemas/                   Pydantic request/response + LLM output validation schemas
  api/v1/endpoints/          REST endpoints (resumes, jobs, matching)
  services/
    extraction/               PDF/DOCX text extraction (+ OCR fallback)
    llm/                       LLM provider interface, GPT-5 implementation, prompts
    embeddings/                Embedding provider interface, OpenAI implementation
    search/                    Hybrid search (pgvector + full-text fusion)
  workers/                    Celery app + ingestion/matching background tasks
alembic/                     DB migrations (first migration enables pgvector + pg_trgm)
deploy/nginx.conf            Reverse proxy config for the VPS
docker-compose.yml           db, redis, api, worker, nginx
```

## First-time setup

```bash
cp .env.example .env        # fill in real secrets and API keys
docker compose build
docker compose up -d db redis
docker compose run --rm api alembic upgrade head
docker compose up -d
```

API available at http://localhost:8000/docs (Swagger UI).

## What's implemented vs. stubbed

Implemented: full request/response flow for resume upload -> ingestion -> JD creation ->
matching -> shortlist retrieval, wired end-to-end through Celery. Auth is implemented:
register/login (JWT, OAuth2 password flow — works with Swagger UI's Authorize button),
`get_current_user` / `require_role()` dependencies, and all resume/job/match endpoints
now require a valid token. `jobs.created_by` is set from the authenticated user.

Deliberately left as TODOs for the next pass:
- Alembic autogenerate hasn't been run against a live DB yet — this environment has no
  network or Postgres available to test against. Run this yourself before trusting the
  hand-written models:
  ```bash
  docker compose up -d db
  docker compose run --rm api alembic revision --autogenerate -m "initial schema"
  docker compose run --rm api alembic upgrade head
  ```
  Review the generated migration file carefully, especially the `vector` and `JSONB`
  column definitions, before applying it anywhere beyond local dev.
- No role-based restriction applied yet beyond the dependency existing — e.g. `require_role("admin")`
  isn't attached to any endpoint yet; decide which routes (if any) should be admin-only.
- Frontend (React) is a separate project, not included here
- Tests (pytest) — not included in this skeleton pass
- Password reset / email verification flow — not in scope for v1 per the original doc

## Notes tying back to the project doc

- `EMBEDDING_DIM` in `models/candidate_embedding.py` is hardcoded to 3072
  (text-embedding-3-large). Changing `EMBEDDING_PROVIDER`/`EMBEDDING_MODEL_NAME` in `.env`
  alone is not enough if the new model has a different dimension — a migration + full
  re-embed of the resume pool is required (see doc Section 3.3).
- `services/search/hybrid_search.py` implements the fusion query from doc Section 8.4.
  Weights are in `.env` (`HYBRID_DENSE_WEIGHT` / `HYBRID_KEYWORD_WEIGHT`) so they can be
  tuned against the validation set without a code change, per Section 8.3 Step 3.
- The synonym/abbreviation layer (Section 8.3 Step 2) and the hard-requirement pre-check
  (Section 8.3 Step 4) are **not yet implemented** — the current hybrid search is the
  baseline version. Both are the natural next additions to `hybrid_search.py`.
