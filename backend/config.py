"""
backend/config.py
全局配置，通过环境变量覆盖默认值。
所有模块 import 时应从此处取配置，严禁硬编码敏感信息。
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Server ──────────────────────────────────────────
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # ── Database ────────────────────────────────────────
    POSTGRES_DSN: str = "postgresql+asyncpg://user:password@localhost:5432/spa_db"
    CHROMA_PERSIST_DIR: str = "./data/chromadb"

    # ── Security ────────────────────────────────────────
    SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION"   # JWT signing key
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24     # 24 h

    # Fernet key for encrypting CAS passwords and LLM API keys stored in DB.
    # Generate with: from cryptography.fernet import Fernet; Fernet.generate_key()
    FERNET_KEY: str = "CHANGE_ME_GENERATE_WITH_FERNET"

    # ── LLM ─────────────────────────────────────────────
    DEEPSEEK_MODEL: str = "deepseek-chat"          # model ID passed to PydanticAI
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_API_KEY: str = ""                     # optional fallback when user has not saved a personal key
    AGENT_RUN_TIMEOUT_SECONDS: int = 300

    # ── File Storage ────────────────────────────────────
    UPLOAD_DIR: str = "./data/uploads"             # raw uploaded files
    MAX_UPLOAD_SIZE_MB: int = 50

    # ── RAG ─────────────────────────────────────────────
    CHUNK_SIZE: int = 512                          # characters per vector chunk
    CHUNK_OVERLAP: int = 64
    # Collections that always get queried regardless of subject routing
    RAG_ALWAYS_QUERY: list[str] = ["other"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
