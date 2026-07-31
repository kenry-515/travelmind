"""
TravelMind Agent — Application Settings
Uses pydantic-settings to load from .env / environment variables.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    # --- App ---
    APP_ENV: str = "development"
    APP_DEBUG: bool = False  # Phase 12.29: 默认关闭，生产安全
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"

    # --- LLM ---
    LLM_PROVIDER: str = "deepseek"
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    LLM_TIMEOUT: float = 60.0
    # deepseek-chat 名称已于 2026-07-24 弃用，对应 deepseek-v4-flash 非思考模式
    LLM_MODEL: str = "deepseek-v4-flash"
    # Phase 16.6: 并发控制 — 限制同时进行的 LLM 调用数，防止触发 429 限流
    LLM_MAX_CONCURRENT: int = 4
    # Phase 16.6: 结构化输出超时倍数 — chat_structured 生成复杂 JSON 需更长时间
    LLM_STRUCTURED_TIMEOUT_MULT: float = 1.5

    # --- Vision ---
    VISION_PROVIDER: str = "kimi"
    MOONSHOT_API_KEY: str = ""
    MOONSHOT_BASE_URL: str = "https://api.moonshot.cn/v1"
    VISION_MODEL: str = "kimi-k2.6"
    VISION_TIMEOUT: float = 60.0
    # 备选视觉服务（未启用）

    # --- Maps ---
    AMAP_API_KEY: str = ""
    AMAP_SIGN_KEY: str = ""  # 数字签名私钥 (optional, only if signing is enabled)
    # Deprecated: Baidu Maps was replaced by Amap. Kept as a no-op for backward
    # compatibility with older .env files. Safe to remove once no longer needed.
    BAIDU_MAP_AK: str = ""

    # --- Weather ---
    OPEN_METEO_BASE_URL: str = "https://api.open-meteo.com"

    # --- Database ---
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/travelmind_db"
    DATABASE_URL_SYNC: str = "postgresql://postgres:postgres@localhost:5432/travelmind_db"

    # --- Session Store ---
    # memory: 仅测试/临时（进程内，重启丢）
    # sqlite: dev 默认（文件持久化，WAL 多 worker 读，零额外依赖）
    # redis:  生产（多 worker，TTL，重启恢复）
    SESSION_STORE: str = "sqlite"
    SESSION_SQLITE_PATH: str = "./.sessions/sessions.db"
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- Chroma ---
    CHROMA_PERSIST_DIR: str = "./chroma_data"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        # .env.example 包含若干备用 key 占位（如 QWEN_* / TENCENT_*），未知字段不再报错。
        "extra": "ignore",
    }


settings = Settings()
