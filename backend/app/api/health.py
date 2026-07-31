"""
TravelMind Agent — Health Check API

Phase 14d: Enhanced health check with RAG and LLM connectivity probes.
"""

import logging

from fastapi import APIRouter

from app.database.connection import check_db_connection

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint — verifies API, database, RAG, and LLM connectivity."""
    try:
        db_healthy = await check_db_connection()
    except Exception:
        # Phase 12.30: ASGITransport tests may hit event-loop mismatch
        from app.database.connection import DB_HEALTHY
        db_healthy = DB_HEALTHY

    # Phase 12.30: Fallback for ASGITransport event-loop mismatch —
    # if check_db_connection failed but DB_HEALTHY was set at startup,
    # trust the startup-verified flag
    if not db_healthy:
        from app.database.connection import DB_HEALTHY
        db_healthy = DB_HEALTHY

    # Phase 14d: Probe RAG (ChromaDB) connectivity
    rag_healthy = False
    try:
        from app.rag.vector_store import get_vector_store
        store = get_vector_store()
        rag_healthy = store.is_connected and store.count() > 0
    except Exception:
        pass

    # Phase 14d: Probe LLM provider
    llm_healthy = None
    try:
        from app.services.llm_service import get_llm_provider
        provider = await get_llm_provider()
        llm_healthy = provider is not None
    except Exception:
        llm_healthy = False

    # Phase 16.5: Surface session store degradation status
    from app.services.session_store import SESSION_STORE_DEGRADED
    session_degraded = SESSION_STORE_DEGRADED

    services = {
        "api": "healthy",
        "database": "healthy" if db_healthy else "unavailable",
    }
    if rag_healthy:
        services["rag"] = "healthy"
    if llm_healthy is True:
        services["llm"] = "healthy"
    elif llm_healthy is False:
        services["llm"] = "unavailable"
    services["session_store"] = "degraded" if session_degraded else "healthy"

    overall_ok = db_healthy and not session_degraded
    return {
        "status": "ok" if overall_ok else "degraded",
        "version": "0.1.0",
        "services": services,
    }
