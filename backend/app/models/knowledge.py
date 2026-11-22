from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import get_settings
from app.core.db import Base

DIM = get_settings().embedding_dim


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(20))  # contract | policy | guide | project
    path: Mapped[str] = mapped_column(Text)
    # Solo para la documentación (kind="guide" o "project"): título, contenido Markdown y origen
    title: Mapped[str | None] = mapped_column(String(200))
    slug: Mapped[str | None] = mapped_column(String(120), unique=True)
    # builtin | upload | agreement (generado del acuerdo con el cliente) | page (escrita en la app)
    source: Mapped[str] = mapped_column(String(20), default="upload", server_default="upload")
    content: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    # Documentación de un proyecto concreto (kind="project")
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    # Calculado en Python (no en la base de datos) para que el valor no quede caducado tras el commit
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(UTC)
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | ready | failed
    error: Mapped[str | None] = mapped_column(Text)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        Index(
            "ix_document_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    content: Mapped[str] = mapped_column(Text)
    # source, section, page: lo que se muestra en la cita
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    embedding: Mapped[list[float]] = mapped_column(Vector(DIM))


class HistoricalTask(Base):
    """Tareas de proyectos anteriores del equipo con sus horas reales: la base para estimar mejor."""

    __tablename__ = "historical_tasks"
    __table_args__ = (
        Index(
            "ix_historical_tasks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(Text)
    task_type: Mapped[str] = mapped_column(String(40), index=True)
    estimated_hours: Mapped[float | None] = mapped_column(Float)
    actual_hours: Mapped[float] = mapped_column(Float)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(DIM))
    # Si viene de un proyecto ejecutado en Holly Manager, la tarea de la que sale
    source_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_tasks.id", ondelete="CASCADE"), unique=True
    )
