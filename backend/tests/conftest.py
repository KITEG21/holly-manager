import hashlib
import os
from collections.abc import Callable
from typing import Any

import pytest

# La base de datos de tests vive en el mismo Postgres de docker-compose
BASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://holly:holly@localhost:5434/holly")
TEST_URL = BASE_URL.rsplit("/", 1)[0] + "/holly_test"
os.environ["DATABASE_URL"] = TEST_URL
# Vacío (no ausente): si no, se leería del .env y los tests enviarían trazas a Jaeger
os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = ""

from pydantic import BaseModel  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.db import Base  # noqa: E402
from app.core.llm import LLMResponse, ToolCall  # noqa: E402

_schema_ready = False


async def _ensure_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    admin = create_async_engine(BASE_URL, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    async with admin.connect() as conn:
        exists = await conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = 'holly_test'"))
        if not exists:
            await conn.execute(text("CREATE DATABASE holly_test"))
    await admin.dispose()

    eng = create_async_engine(TEST_URL, poolclass=NullPool)
    async with eng.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("DROP FUNCTION IF EXISTS forbid_requirement_version_change CASCADE"))
        await conn.execute(
            text(
                "CREATE FUNCTION forbid_requirement_version_change() RETURNS trigger AS $$ "
                "BEGIN RAISE EXCEPTION 'requirement_versions es inmutable'; END; $$ LANGUAGE plpgsql"
            )
        )
        await conn.execute(
            text(
                "CREATE TRIGGER requirement_versions_immutable BEFORE UPDATE OR DELETE ON requirement_versions "
                "FOR EACH ROW EXECUTE FUNCTION forbid_requirement_version_change()"
            )
        )
    await eng.dispose()
    _schema_ready = True


@pytest.fixture
async def session():
    await _ensure_schema()
    eng = create_async_engine(TEST_URL, poolclass=NullPool)
    async with eng.begin() as conn:
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        # El trigger impide DELETE, pero TRUNCATE no dispara triggers de fila
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    async with async_sessionmaker(eng, expire_on_commit=False)() as s:
        yield s
    await eng.dispose()


def fake_vector(text_: str, dim: int = 768) -> list[float]:
    """Embedding determinista: textos iguales → vectores iguales."""
    digest = hashlib.sha256(text_.encode()).digest()
    return [((digest[i % len(digest)] + i) % 17) / 17 + 0.01 for i in range(dim)]


class FakeLLM:
    """LLM guionizado. `chat` consume respuestas en orden; `structured` usa una función por esquema."""

    def __init__(self) -> None:
        self.chat_script: list[LLMResponse | Callable[[list[dict]], LLMResponse]] = []
        self.structured_handlers: dict[type, Callable[[list[dict]], Any]] = {}
        self.chat_calls: list[list[dict]] = []

    def say(self, content: str) -> "FakeLLM":
        self.chat_script.append(LLMResponse(content=content))
        return self

    def call(self, name: str, **arguments: Any) -> "FakeLLM":
        self.chat_script.append(
            LLMResponse(tool_calls=[ToolCall(id=f"c{len(self.chat_script)}", name=name, arguments=arguments)])
        )
        return self

    async def chat(self, messages, tools=None) -> LLMResponse:
        self.chat_calls.append(list(messages))
        if not self.chat_script:
            raise AssertionError("FakeLLM: no quedan respuestas guionizadas")
        nxt = self.chat_script.pop(0)
        return nxt(messages) if callable(nxt) else nxt

    async def structured(self, messages, schema: type[BaseModel]):
        return self.structured_handlers[schema](messages)

    async def embed(self, texts: list[str], purpose: str = "document") -> list[list[float]]:
        return [fake_vector(t) for t in texts]


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()
