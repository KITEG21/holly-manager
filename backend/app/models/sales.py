from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Stage(StrEnum):
    qualification = "qualification"
    requirements = "requirements"
    estimating = "estimating"
    commercial = "commercial"
    closed = "closed"
    nurture = "nurture"
    discarded = "discarded"


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(255))
    stage: Mapped[str] = mapped_column(String(20), default=Stage.qualification)
    qualification_status: Mapped[str] = mapped_column(String(20), default="pending")
    qualification_score: Mapped[float | None] = mapped_column(Float)
    qualification_detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # user | assistant | human
    agent: Mapped[str | None] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text)
    # trace_id, herramientas usadas, reglas aplicadas, citas...
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RequirementDraft(Base):
    __tablename__ = "requirement_drafts"

    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), primary_key=True)
    doc: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RequirementVersion(Base):
    """Acuerdo confirmado por el cliente. Un trigger en la base de datos impide modificarlo o borrarlo."""

    __tablename__ = "requirement_versions"
    __table_args__ = (UniqueConstraint("lead_id", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    doc: Mapped[dict[str, Any]] = mapped_column(JSONB)
    sha256: Mapped[str] = mapped_column(String(64))
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Estimate(Base):
    __tablename__ = "estimates"

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    requirement_version_id: Mapped[int] = mapped_column(ForeignKey("requirement_versions.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | running | done | failed
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    estimate_id: Mapped[int] = mapped_column(ForeignKey("estimates.id"))
    terms: Mapped[dict[str, Any]] = mapped_column(JSONB)
    valid: Mapped[bool] = mapped_column(Boolean)
    violations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Escalation(Base):
    __tablename__ = "escalations"

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    client_request: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    violations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | resolved
    resolution: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Proposal(Base):
    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | ready | failed
    pdf_path: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
