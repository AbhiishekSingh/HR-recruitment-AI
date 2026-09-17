from fastapi import APIRouter

from app.api.v1.endpoints import candidates, jobs, matching, auth, companies, assessments, analytics

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(companies.router, prefix="/companies", tags=["companies"])
api_router.include_router(candidates.router, prefix="/candidates", tags=["candidates"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(matching.router, prefix="/jobs", tags=["ai-matching"])  # existing GPT-5 pipeline, not yet wired into ATS flow
api_router.include_router(assessments.router, prefix="", tags=["assessments"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
