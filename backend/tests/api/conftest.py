"""
API 集成测试 — 共享 fixtures 和配置

Phase 12.30: 真实 DB 测试模式 — 不再覆盖 get_db，测试走真实 PostgreSQL。
"""

import pytest
from app.main import create_app


@pytest.fixture(scope="session")
def app():
    """FastAPI 应用实例（真实 DB 模式）。"""
    return create_app()
