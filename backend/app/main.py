"""
TravelMind Agent — FastAPI Application Entry Point (Phase 18 P3 生产级)

新增 Phase 18 P3:
  - GZip 中间件 (response compression)
  - /metrics 端点 (无 Prometheus 依赖, 轻量自实现)
  - 健康检查细分 (/health/live, /health/ready)
  - HTTPException 统一 handler
  - Request ID 中间件 (Phase 12.29)
  - 限流 (Phase 12.28c)
  - 日志 JSON (生产)
  - 优雅关闭
"""

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

# Phase 12.29e: Prometheus /metrics（可选）
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    _HAS_PROMETHEUS = True
except ImportError:
    _HAS_PROMETHEUS = False
    Instrumentator = None

from app.api import api_router
from app.api.errors import (
    APIError,
    api_error_handler,
    http_exception_handler,
)
from app.config.settings import settings
from app.database.connection import engine
from app.database.models import Base
from app.middleware import RequestIDMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.metrics import MetricsStore, get_metrics_response

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ATTRACTIONS_FILE = DATA_DIR / "attractions.json"

# 全局 metrics store (Phase 18 P3 自实现, 不依赖 prometheus 库)
metrics_store = MetricsStore()


def setup_logging():
    """Configure application logging.

    Phase 12.29e: 生产环境使用 JSON 格式 + request_id 注入;
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
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)


def _init_rag() -> bool:
    """Initialize the RAG system on startup."""
    try:
        from app.rag import init_rag_from_data
        return init_rag_from_data(ATTRACTIONS_FILE)
    except Exception as e:
        logger.warning(f"RAG initialization failed: {e} — RAG disabled")
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup / shutdown lifecycle."""
    from app.database.connection import check_db_connection
    db_ok = await check_db_connection()
    if db_ok:
        logger.info("Database connection verified.")
    else:
        logger.warning("Database unavailable — history/favorites disabled.")

    if settings.APP_ENV == "development":
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created successfully (dev auto-create).")
        except Exception as e:
            logger.warning(
                f"Database not available, skipping table creation: {e}"
            )

    _init_rag()
    metrics_store.mark_started()

    yield

    # Phase 18 P3: 优雅关闭
    logger.info("Shutting down — closing ChromaDB and DB pool")
    metrics_store.mark_stopped()

    try:
        from app.rag.vector_store import get_vector_store
        store = get_vector_store()
        if store.is_connected:
            store.close()
    except Exception as e:
        logger.warning(f"ChromaDB close error (non-fatal): {e}")
    await engine.dispose()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    """FastAPI application factory."""
    setup_logging()

    app = FastAPI(
        title="TravelMind Agent API",
        description=(
            "AI-powered multi-agent travel planning system (Phase 18 P3 生产级).\n\n"
            "## 主要模块\n"
            "- **chat**: 真实 LLM 多 agent 对话\n"
            "- **resources**: 景区资源调度管理 (11 区全覆盖)\n"
            "- **guide**: AI 智能讲解\n"
            "- **itineraries**: 行程生成 / 持久化\n"
            "- **favorites**: 收藏管理\n"
            "- **image**: 景点图片识别\n"
            "- **weather**: 旅游天气建议\n"
            "- **recommend**: 推荐系统\n\n"
            "## 错误格式\n"
            "所有错误响应统一为 `{\"error\": {\"code\", \"message\", \"suggestion\", \"retryable\"}}`。"
        ),
        version="0.3.0",
        lifespan=lifespan,
        contact={
            "name": "TravelMind Team",
            "url": "https://github.com/kenry-515/travelmind",
        },
        license_info={
            "name": "MIT",
        },
    )

    # OpenAPI tags 元数据 (Phase 18 P3)
    openapi_tags = [
        {"name": "health", "description": "健康检查 (live/ready)"},
        {"name": "chat", "description": "对话 (agent 主导)"},
        {"name": "agent", "description": "智能体 (profile/slot/narrate)"},
        {"name": "recommend", "description": "推荐系统 (quick/detailed)"},
        {"name": "weather", "description": "天气查询 + 旅游建议"},
        {"name": "image", "description": "图片识别"},
        {"name": "dialog", "description": "对话编排 (message/generate)"},
        {"name": "itineraries", "description": "行程管理"},
        {"name": "favorites", "description": "收藏管理"},
        {"name": "guide", "description": "AI 讲解 (featured/search/narration)"},
        {"name": "resources", "description": "景区资源调度 (P0+P1+P2 全套)"},
        {"name": "monitoring", "description": "监控指标 (Phase 18 P3)"},
    ]
    app.openapi_tags = openapi_tags

    # 中间件顺序: CORS > RequestID > GZip > 限流 > body limit
    app.add_middleware(RequestIDMiddleware)

    cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Device-ID", "X-Request-ID"],
    )

    # Phase 18 P3: GZip 压缩 (responses > 1KB)
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    # 请求体大小限制
    @app.middleware("http")
    async def limit_request_body(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and request.url.path.startswith("/api/v1/") and "image" not in request.url.path:
            try:
                if int(content_length) > 1024 * 1024:  # 1MB
                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": {
                                "code": "PAYLOAD_TOO_LARGE",
                                "message": "请求体过大，JSON 端点限制 1MB",
                                "suggestion": "请减小请求体大小或分批提交",
                                "retryable": False,
                            }
                        },
                    )
            except (ValueError, TypeError):
                pass
        return await call_next(request)

    # Phase 18 P3: 监控中间件 — 记录每个 endpoint 耗时
    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration = time.time() - start
        path = request.url.path
        method = request.method
        status = response.status_code
        # 跳过 /metrics 和 /health (避免 self-instrumenting)
        if not path.startswith("/api/v1/metrics") and not path.startswith("/api/v1/health"):
            metrics_store.record_request(method, path, status, duration)
        return response

    # Mount API routes
    app.include_router(api_router)

    # 错误 handler (Phase 18 P3: APIError + HTTPException + RequestValidationError 统一格式)
    app.add_exception_handler(APIError, api_error_handler)  # type: ignore[arg-type]
    from fastapi import HTTPException
    from fastapi.exceptions import RequestValidationError
    app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, http_exception_handler)  # type: ignore[arg-type]

    # Phase 12.29e: Prometheus /metrics（可选）
    if _HAS_PROMETHEUS and Instrumentator is not None:
        Instrumentator().instrument(app).expose(app)

    # Phase 18 P3: 限流 (per-IP 默认 60 req/min + per-endpoint 特殊策略)
    # 重型 endpoint (行程生成/calendar) 单独限制, 防止被刷爆
    app.add_middleware(
        RateLimitMiddleware,
        rate=60,
        per_seconds=60,
        per_endpoint={
            "/api/v1/dialog/generate": (10, 60),    # 行程生成: 10 req/min
            "/api/v1/resources/calendar": (30, 60),  # calendar: 30 req/min
            "/api/v1/image/analyze": (20, 60),       # 图片识别: 20 req/min
        },
    )

    return app


app = create_app()