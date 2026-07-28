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
    db_healthy = await check_db_connection()

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

    return {
        "status": "ok" if db_healthy else "degraded",
        "version": "0.1.0",
        "services": services,
    }
