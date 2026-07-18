"""
TravelMind Agent — FastAPI Application Entry Point
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.config.settings import settings
from app.database.connection import engine
from app.database.models import Base
from app.middleware import RequestIDMiddleware

logger = logging.getLogger(__name__)

# Path to the final attractions knowledge base
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ATTRACTIONS_FILE = DATA_DIR / "attractions.json"


def setup_logging():
    """Configure application logging."""
    logging.basicConfig(
        level=logging.DEBUG if settings.APP_DEBUG else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Quiet down noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)


def _init_rag() -> bool:
    """Initialize the RAG system on startup.

    Loads attractions data, fits the TF-IDF embedding provider,
    and connects Chroma vector store. Called once at application startup.

    Returns True on success, False if RAG is unavailable.
    """
    try:
        from app.rag import init_rag_from_data
        return init_rag_from_data(ATTRACTIONS_FILE)
    except Exception as e:
        logger.warning(f"RAG initialization failed: {e} — RAG disabled")
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup / shutdown lifecycle."""
    # Startup: auto-create tables in development only.
    if settings.APP_ENV == "development":
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created successfully (dev auto-create).")
        except Exception as e:
            logger.warning(
                f"Database not available, skipping table creation: {e}"
            )

    # Initialize RAG (embedding provider + Chroma connection)
    _init_rag()

    yield
    # Shutdown: dispose engine
    await engine.dispose()


def create_app() -> FastAPI:
    """FastAPI application factory."""
    setup_logging()

    app = FastAPI(
        title="TravelMind Agent API",
        description="AI-powered multi-agent travel planning system",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Request ID + logging middleware
    app.add_middleware(RequestIDMiddleware)

    # CORS — allow frontend dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount API routes
    app.include_router(api_router)

    return app


app = create_app()
