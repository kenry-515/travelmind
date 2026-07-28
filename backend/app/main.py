"""
TravelMind Agent — FastAPI Application Entry Point
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Phase 12.29e: Prometheus /metrics（可选 — 无依赖时跳过）
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    _HAS_PROMETHEUS = True
except ImportError:
    _HAS_PROMETHEUS = False

from app.api import api_router
from app.api.errors import APIError, api_error_handler
from app.config.settings import settings
from app.database.connection import engine
from app.database.models import Base
from app.middleware import RequestIDMiddleware
from app.middleware.rate_limit import RateLimitMiddleware

logger = logging.getLogger(__name__)

# Path to the final attractions knowledge base
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ATTRACTIONS_FILE = DATA_DIR / "attractions.json"


def setup_logging():
    """Configure application logging.

    Phase 12.29e: 生产环境使用 JSON 格式 + request_id 注入；
    开发环境保持终端友好的纯文本格式。
    """
    if settings.APP_ENV == "production" or settings.APP_ENV == "staging":
        try:
            from pythonjsonlogger import jsonlogger
            handler = logging.StreamHandler()
            fmt = jsonlogger.JsonFormatter(
                fmt="%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            handler.setFormatter(fmt)
            root = logging.getLogger()
            root.addHandler(handler)
            root.setLevel(logging.INFO)
        except ImportError:
            _setup_plain_logging()
    else:
        _setup_plain_logging()


def _setup_plain_logging():
    """Plain text logging for development."""
    logging.basicConfig(
        level=logging.DEBUG if settings.APP_DEBUG else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Quiet down noisy third-party loggers
    # (openai/httpcore log full request bodies at DEBUG — including base64
    # image payloads from the vision service)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
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
    # Check database connectivity first (sets DB_HEALTHY flag)
    from app.database.connection import check_db_connection
    db_ok = await check_db_connection()
    if db_ok:
        logger.info("Database connection verified.")
    else:
        logger.warning("Database unavailable — history/favorites disabled.")

    # Auto-create tables in development (Alembic preferred for production).
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
    # Shutdown: close ChromaDB gracefully (Phase 12.28c) then dispose engine
    try:
        from app.rag.vector_store import get_vector_store
        store = get_vector_store()
        if store.is_connected:
            store.close()
    except Exception:
        pass
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

    # CORS — allow frontend dev server (Phase 12.29: configurable via settings)
    cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Device-ID", "X-Request-ID"],
    )

    # Mount API routes
    app.include_router(api_router)

    # Unified error handler (Phase 12.28c)
    app.add_exception_handler(APIError, api_error_handler)

    # Phase 12.29e: Prometheus /metrics endpoint（可选）
    if _HAS_PROMETHEUS:
        Instrumentator().instrument(app).expose(app)

    # Rate limiting (Phase 12.28c) — 60 req/min per IP, health check exempt
    app.add_middleware(RateLimitMiddleware, rate=60, per_seconds=60)

    # 请求体大小限制（Phase 12.29c）— JSON 端点限制 1MB，图片端点由 upload 中间件控制
    @app.middleware("http")
    async def limit_request_body(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and request.url.path.startswith("/api/v1/") and "image" not in request.url.path:
            try:
                if int(content_length) > 1024 * 1024:  # 1MB
                    return JSONResponse(
                        status_code=413,
                        content={"error": {"code": "PAYLOAD_TOO_LARGE", "message": "请求体过大，JSON 端点限制 1MB"}},
                    )
            except (ValueError, TypeError):
                pass
        return await call_next(request)

    return app


app = create_app()
