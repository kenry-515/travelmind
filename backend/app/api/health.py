"""
TravelMind Agent — Health Check API
"""

from fastapi import APIRouter

from app.database.connection import check_db_connection

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint — verifies API and database connectivity."""
    db_healthy = await check_db_connection()

    return {
        "status": "ok" if db_healthy else "degraded",
        "version": "0.1.0",
        "services": {
            "api": "healthy",
            "database": "healthy" if db_healthy else "unavailable",
        },
    }
