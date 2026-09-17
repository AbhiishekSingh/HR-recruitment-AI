from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.config import settings

app = FastAPI(
    title="AI Resume Screening System",
    version="1.0.0",
)

# NOTE: allow_credentials=True cannot be combined with allow_origins=["*"] per the
# CORS spec — browsers reject that combination outright. In dev, the Vite proxy
# (frontend/vite.config.ts) avoids cross-origin requests entirely, which is why a
# wildcard origin appeared to work before. Listing explicit origins here is what
# makes direct (non-proxied) frontend-to-backend calls actually work too.
DEV_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=DEV_ORIGINS if settings.app_env == "development" else [],  # tighten for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}
