"""
API 集成测试 — 共享 fixtures 和配置
"""

import pytest
from app.main import create_app


@pytest.fixture(scope="session")
def app():
    """FastAPI 应用实例（TestClient 用）。"""
    return create_app()
