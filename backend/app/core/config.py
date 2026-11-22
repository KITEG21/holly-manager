from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    database_url: str = "postgresql+asyncpg://holly:holly@localhost:5434/holly"
    redis_url: str = "redis://localhost:6380/0"

    gemini_api_key: str | None = None
    primary_model: str = "gemini/gemini-3.8-flash"
    secondary_model: str | None = "gemini/gemini-3.1-flash-lite"
    fallback_model: str = "ollama_chat/qwen2.5:7b"
    # Claude (Anthropic) y Codex/GPT (OpenAI): se usan si tienen clave
    anthropic_api_key: str | None = None
    claude_model: str = "anthropic/claude-sonnet-5-5"
    openai_api_key: str | None = None
    openai_model: str = "openai/gpt-5"
    # Orden de la cadena de respaldo; se salta cualquier proveedor sin credenciales
    llm_chain: str = "gemini,gemini_secondary,claude,openai,ollama"
    ollama_api_base: str = "http://localhost:11600"
    embedding_model: str = "ollama/nomic-embed-text"
    embedding_dim: int = 768
    # Umbral de similitud para usar el histórico al estimar (calibrado para nomic-embed-text)
    history_min_similarity: float = 0.6

    otel_exporter_otlp_endpoint: str | None = None
    service_name: str = "holly-manager"

    # Nombre que ven los clientes en el chat, los agentes y la propuesta
    company_name: str = "Holly"

    # Cambiar en producción: firma los tokens de sesión
    secret_key: str = "dev-secret-change-me"
    token_ttl_hours: int = 12

    storage_dir: Path = Path("storage")
    # Documentación incluida en el repositorio (Markdown), sincronizada con la sección Documentation
    docs_dir: Path = Path(__file__).resolve().parents[2] / "docs"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:5174"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
