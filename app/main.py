"""
NarcTrace backend FastAPI application (SIH26231).

Run (dev):  uvicorn app.main:app --reload --port 8000
Run (prod): gunicorn -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:$PORT app.main:app

PRESUMPTIVE FIELD-TEST RESULT ONLY. All kit profiles/thresholds are SIMULATED / PROXY.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.constants import STANDARD_DISCLAIMER
from app.api.routes import router as api_router

settings = get_settings()

app = FastAPI(
    title="NarcTrace Backend",
    version=settings.APP_VERSION,
    description=(
        "Deterministic colour-science pipeline for field drug-test digital companion. "
        + STANDARD_DISCLAIMER
    ),
)

# CORS restricted to configured origins (never '*').
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/")
def root() -> dict:
    return {
        "service": "narctrace-backend",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/api/health",
        "disclaimer": STANDARD_DISCLAIMER,
    }
