"""
TravelMind Agent — Application Settings
Uses pydantic-settings to load from .env / environment variables.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    # --- App ---
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    # --- LLM ---
    LLM_PROVIDER: str = "deepseek"
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    LLM_TIMEOUT: float = 60.0
    LLM_MODEL: str = "deepseek-chat"

    # --- Vision ---
    VISION_PROVIDER: str = "kimi"
    MOONSHOT_API_KEY: str = ""
    MOONSHOT_BASE_URL: str = "https://api.moonshot.cn/v1"
    VISION_MODEL: str = "kimi-k2.6"
    VISION_TIMEOUT: float = 60.0
    # 备选视觉服务（未启用）
    QWEN_API_KEY: str = ""
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    TENCENT_SECRET_ID: str = ""
    TENCENT_SECRET_KEY: str = ""

    # --- Maps ---
    AMAP_API_KEY: str = ""
    AMAP_SIGN_KEY: str = ""  # 数字签名私钥 (optional, only if signing is enabled)
    # Deprecated: Baidu Maps was replaced by Amap. Kept as a no-op so older
    # .env files containing BAIDU_MAP_AK don't fail settings validation
    # (extra=forbid). Safe to remove once .env no longer has it.
    BAIDU_MAP_AK: str = ""

    # --- Weather ---
    OPEN_METEO_BASE_URL: str = "https://api.open-meteo.com"

    # --- Database ---
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/travelmind_db"
    DATABASE_URL_SYNC: str = "postgresql://postgres:postgres@localhost:5432/travelmind_db"

    # --- Chroma ---
    CHROMA_PERSIST_DIR: str = "./chroma_data"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


settings = Settings()
