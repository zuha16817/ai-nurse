"""
AI Nurse - Conversational Patient Triage & Severity Assessment System
Main FastAPI application entry point.
"""

import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import conversations, triage, patients, audit, staff, auth
from app.models.database import init_db
from app.services.rag.knowledge import get_knowledge_service
from app.core.config import get_settings

settings = get_settings()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple in-memory sliding-window rate limiter (spec §32). A prototype-scale
    single-process limiter - a production deployment behind multiple workers would
    move this to a shared store (e.g. Redis), but the requirement here is that
    RATE_LIMIT_PER_MINUTE is actually enforced, not just declared in config.
    """

    def __init__(self, app, requests_per_minute: int):
        super().__init__(app)
        self.limit = requests_per_minute
        self.hits: dict = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window = self.hits[client_ip]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= self.limit:
            return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
        window.append(now)
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    await init_db()
    ks = get_knowledge_service()
    await ks.initialize()
    yield


app = FastAPI(
    title="AI Nurse - Patient Triage System",
    description=(
        "Conversational patient triage and severity assessment. "
        "LLM extracts clinical facts; deterministic rules engine decides acuity."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# CORS - in production lock down to your domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RateLimitMiddleware, requests_per_minute=settings.RATE_LIMIT_PER_MINUTE)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)

# Routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(patients.router, prefix="/api/patients", tags=["Patients"])
app.include_router(conversations.router, prefix="/api/conversations", tags=["Conversations"])
app.include_router(triage.router, prefix="/api/triage", tags=["Triage"])
app.include_router(staff.router, prefix="/api/staff", tags=["Staff"])
app.include_router(audit.router, prefix="/api/audit", tags=["Audit"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "ai-nurse"}
