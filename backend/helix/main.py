"""Helix FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from helix.api.routes_assessment import router as assessment_router
from helix.api.routes_session import router as session_router
from helix.db.database import create_tables
from helix.scoring import registry
from helix.scoring.instruments import _DEFINITIONS_DIR


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables and auto-discover scorers."""
    create_tables()
    registry.auto_discover(_DEFINITIONS_DIR)
    yield


app = FastAPI(
    title="Helix",
    description="Psychological self-exploration API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev only — restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(session_router)
app.include_router(assessment_router)


@app.get("/health", tags=["meta"])
def health():
    """Health check."""
    return {"status": "ok"}
