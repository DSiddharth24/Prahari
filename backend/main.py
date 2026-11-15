"""Main FastAPI application entrypoint for Prahari."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.engine_bridge import init_db
from backend.api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager."""
    init_db()
    yield


app = FastAPI(
    title="Prahari Security Alert Triage API",
    description="API for AI-assisted alert correlation, triage, and regulatory reporting.",
    version="0.1.0",
    lifespan=lifespan,
)

# Enable CORS for frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routes
app.include_router(router)
