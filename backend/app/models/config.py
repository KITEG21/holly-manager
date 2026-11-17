from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class TaskType(Base):
    __tablename__ = "task_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True)
    min_hours: Mapped[float] = mapped_column(Float)
    max_hours: Mapped[float] = mapped_column(Float)
    complexity: Mapped[str] = mapped_column(String(10))


class QualificationCriterion(Base):
    __tablename__ = "qualification_criteria"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True)
    question: Mapped[str] = mapped_column(Text)
    weight: Mapped[float] = mapped_column(Float)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class AppSetting(Base):
    """Configuración singleton (equipo, reglas comerciales, umbrales), validada con Pydantic al leer y escribir."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
