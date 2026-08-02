"""
TravelMind Agent — Health Check API (Phase 18 P3 生产级)

Phase 18 P3 新增:
  - /health/live   — Kubernetes liveness probe (进程存活)
  - /health/ready  — Kubernetes readiness probe (依赖就绪)
  - /health        — 完整健康信息 (兼容旧 API)
  - /metrics       — Prometheus metrics
"""

import logging

from fastapi import APIRouter, Response

from app.database.connection import check_db_connection

logger = logging.getLogger(__name__)

router = APIRouter()


async def _service_status() -> dict:
    """统一服务状态检测 (避免重复代码)。"""
    try:
        db_healthy = await check_db_connection()
    except Exception:
        from app.database.connection import DB_HEALTHY
        db_healthy = DB_HEALTHY

    if not db_healthy:
        from app.database.connection import DB_HEALTHY
        db_healthy = DB_HEALTHY

    rag_healthy = False
    try:
        from app.rag.vector_store import get_vector_store
        store = get_vector_store()
        rag_healthy = store.is_connected and store.count() > 0
    except Exception:
        pass

    llm_healthy = None
    try:
        from app.services.llm_service import get_llm_provider
        provider = await get_llm_provider()
        llm_healthy = provider is not None
    except Exception:
        llm_healthy = False

    from app.services.session_store import SESSION_STORE_DEGRADED
    session_degraded = SESSION_STORE_DEGRADED

    services = {
        "api": "healthy",
        "database": "healthy" if db_healthy else "unavailable",
        "rag": "healthy" if rag_healthy else "unavailable",
        "llm": "healthy" if llm_healthy else ("unavailable" if llm_healthy is False else "unknown"),
        "session_store": "degraded" if session_degraded else "healthy",
    }
    overall_ok = db_healthy and not session_degraded
    return {
        "status": "ok" if overall_ok else "degraded",
        "services": services,
        "db_healthy": db_healthy,
        "rag_healthy": rag_healthy,
        "llm_healthy": llm_healthy,
    }


@router.get("/health")
async def health_check():
    """完整健康检查 (兼容 Phase 14d 接口)。"""
    info = await _service_status()
    return {
        "status": info["status"],
        "version": "0.3.0",
        "services": info["services"],
    }


@router.get("/health/live")
async def liveness():
    """Kubernetes liveness probe — 仅检查进程存活。

    返回 200 = 进程在跑 (即使依赖项坏了也不该重启, 否则可能死循环)
    """
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness():
    """Kubernetes readiness probe — 检查依赖项。

    返回 200 = 依赖项就绪 (DB / LLM / RAG), 可以接受流量
    返回 503 = 依赖项不可用, 应从 LB 摘除
    """
    info = await _service_status()
    if info["db_healthy"] and info["llm_healthy"]:
        return {"status": "ready", "services": info["services"]}
    return Response(
        status_code=503,
        content={"status": "not_ready", "services": info["services"]},
    )


@router.get("/metrics")
async def metrics():
    """Prometheus metrics 端点 (Phase 18 P3 自实现, 无依赖)。"""
    from app.main import metrics_store
    return Response(
        content=metrics_store.render(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )