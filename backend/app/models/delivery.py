from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Role(StrEnum):
    client = "client"
    developer = "developer"
    admin = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    # Solo para clientes: su conversación comercial
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TaskStatus(StrEnum):
    todo = "todo"
    in_progress = "in_progress"
    done = "done"


class ProjectTask(Base):
    """Tarea del backlog de un proyecto confirmado; nace de la estimación y la ejecuta el equipo."""

    __tablename__ = "project_tasks"
    __table_args__ = (UniqueConstraint("estimate_id", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    estimate_id: Mapped[int] = mapped_column(ForeignKey("estimates.id"))
    key: Mapped[str] = mapped_column(String(20))  # T1, T2...
    story_id: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(Text)
    task_type: Mapped[str] = mapped_column(String(40))
    depends_on: Mapped[list[str]] = mapped_column(JSONB, default=list)
    sprint: Mapped[int] = mapped_column(Integer)
    planned_hours: Mapped[float] = mapped_column(Float)
    actual_hours: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(20), default=TaskStatus.todo)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TimeEntry(Base):
    __tablename__ = "time_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("project_tasks.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    hours: Mapped[float] = mapped_column(Float)
    # Día en que se hizo el trabajo (la hoja de horas agrupa por aquí), no cuándo se registró
    work_date: Mapped[date] = mapped_column(Date, server_default=func.current_date(), index=True)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
