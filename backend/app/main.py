"""
FastAPI application entry point.
"""
from __future__ import annotations

import logging
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import create_all_tables
from app.routers import admin, challenges, chat, config, documents, lti
from app.services.key_service import load_keys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)
log = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    log.info("🚀 Starting LTI Virtual Tutor backend (env=%s)", settings.app_env)

    # Ensure data directory exists
    Path("./data").mkdir(exist_ok=True)

    # Load / generate RSA keys for LTI
    load_keys()

    # Create DB tables
    await create_all_tables()
    log.info("✅ Database ready")

    yield  # ← Application runs here

    log.info("🛑 Shutting down")


app = FastAPI(
    title="LTI Virtual Tutor",
    description="LTI 1.3 Virtual Tutor for Open edX — backend API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ──────────────────────────────────────────────────────────────────
app.include_router(lti.router)
app.include_router(chat.router)
app.include_router(config.router)
app.include_router(documents.router)
app.include_router(challenges.router)
app.include_router(admin.router)


# ─── Health ───────────────────────────────────────────────────────────────────
@app.get("/api/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "lti-virtual-tutor", "version": "1.0.0"}


# ─── Dev runner ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.is_development,
    )
