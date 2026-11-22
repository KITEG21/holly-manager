import asyncio
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.agents.router import handle_message
from app.api.deps import AdminOnly, lead_access
from app.core.db import SessionLocal, get_session
from app.core.llm import get_llm
from app.models import Estimate, Lead, Message, Proposal, RequirementDraft, RequirementVersion, Stage
from app.schemas.requirements import RequirementDoc

router = APIRouter(prefix="/api/leads", tags=["leads"])
Session = Depends(get_session)
OwnLead = Depends(lead_access)


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: str | None
    stage: str
    qualification_status: str
    qualification_score: float | None
    created_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    role: str
    agent: str | None
    content: str
    created_at: datetime


class MessageInternal(MessageOut):
    meta: dict[str, Any]


async def get_lead(session: AsyncSession, lead_id: int) -> Lead:
    lead = await session.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(404, "client not found")
    return lead


@router.get("", dependencies=[AdminOnly])
async def list_leads(session: AsyncSession = Session) -> list[LeadOut]:
    rows = (await session.scalars(select(Lead).order_by(Lead.id.desc()))).all()
    return [LeadOut.model_validate(r) for r in rows]


# --- Vista del cliente -------------------------------------------------------------------------


@router.get("/{lead_id}/messages", dependencies=[OwnLead])
async def client_messages(lead_id: int, session: AsyncSession = Session) -> list[MessageOut]:
    """Lo que ve el cliente: sin meta interna (reglas, herramientas, trazas)."""
    rows = (
        await session.scalars(select(Message).where(Message.lead_id == lead_id).order_by(Message.id))
    ).all()
    return [MessageOut.model_validate(m) for m in rows]


class ChatIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


@router.post("/{lead_id}/chat", dependencies=[OwnLead])
async def chat(lead_id: int, data: ChatIn) -> EventSourceResponse:
    """Ejecuta un turno y emite por SSE los cambios (documento de requisitos, cualificación, escalados)."""
    queue: asyncio.Queue[tuple[str, Any] | None] = asyncio.Queue()

    async def emit(event: str, payload: Any) -> None:
        await queue.put((event, payload))

    async def run_turn() -> None:
        try:
            async with SessionLocal() as session:
                lead = await get_lead(session, lead_id)
                msg = await handle_message(session, get_llm(), lead, data.content, emit)
                await emit("stage", lead.stage)
                await emit("message", MessageOut.model_validate(msg).model_dump(mode="json"))
        except Exception as e:  # noqa: BLE001  el error llega al cliente como evento
            await emit("error", {"detail": str(e)})
        finally:
            await queue.put(None)

    async def events():
        task = asyncio.create_task(run_turn())
        while (item := await queue.get()) is not None:
            event, payload = item
            yield {"event": event, "data": json.dumps(payload, default=str, ensure_ascii=False)}
        await task

    return EventSourceResponse(events())


class LeadState(BaseModel):
    lead: LeadOut
    draft: RequirementDoc | None
    readiness_problems: list[str]
    confirmed_version: int | None
    proposals: list[dict[str, Any]]


@router.get("/{lead_id}/state", dependencies=[OwnLead])
async def lead_state(lead_id: int, session: AsyncSession = Session) -> LeadState:
    lead = await get_lead(session, lead_id)
    draft = await session.get(RequirementDraft, lead_id)
    doc = RequirementDoc.model_validate(draft.doc) if draft else None
    version = await session.scalar(
        select(func.max(RequirementVersion.version)).where(RequirementVersion.lead_id == lead_id)
    )
    proposals = (await session.scalars(select(Proposal).where(Proposal.lead_id == lead_id))).all()
    return LeadState(
        lead=LeadOut.model_validate(lead),
        draft=doc,
        readiness_problems=doc.readiness_problems() if doc else ["There is no document yet."],
        confirmed_version=version,
        proposals=[{"id": p.id, "status": p.status} for p in proposals],
    )


@router.post("/{lead_id}/requirements/confirm", dependencies=[OwnLead])
async def confirm_requirements(lead_id: int, session: AsyncSession = Session) -> dict[str, int]:
    """El cliente confirma el resumen: se congela como versión inmutable y arranca la estimación."""
    from app.tasks.estimation import estimate_project
    from app.tasks.ingest import sync_agreement_doc_task

    lead = await get_lead(session, lead_id)
    if lead.stage != Stage.requirements:
        raise HTTPException(409, f"the client is in the '{lead.stage}' stage")
    draft = await session.get(RequirementDraft, lead_id)
    doc = RequirementDoc.model_validate(draft.doc) if draft else RequirementDoc()
    if problems := doc.readiness_problems():
        raise HTTPException(422, {"problems": problems})

    canonical = json.dumps(doc.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    last = await session.scalar(
        select(func.max(RequirementVersion.version)).where(RequirementVersion.lead_id == lead_id)
    )
    version = RequirementVersion(
        lead_id=lead_id,
        version=(last or 0) + 1,
        doc=json.loads(canonical),
        sha256=hashlib.sha256(canonical.encode()).hexdigest(),
    )
    session.add(version)
    await session.flush()
    estimate = Estimate(lead_id=lead_id, requirement_version_id=version.id)
    session.add(estimate)
    lead.stage = Stage.estimating
    session.add(
        Message(
            lead_id=lead_id,
            role="assistant",
            agent="requirements",
            content=f"Agreement confirmed (version {version.version})! The team is preparing the estimate.",
        )
    )
    await session.commit()
    estimate_project.delay(estimate.id)
    sync_agreement_doc_task.delay(lead_id)
    return {"version": version.version, "estimate_id": estimate.id}


@router.get("/{lead_id}/proposals/{proposal_id}/pdf", dependencies=[OwnLead])
async def proposal_pdf(lead_id: int, proposal_id: int, session: AsyncSession = Session) -> FileResponse:
    p = await session.get(Proposal, proposal_id)
    if p is None or p.lead_id != lead_id or p.status != "ready" or not p.pdf_path:
        raise HTTPException(404, "proposal not available")
    return FileResponse(Path(p.pdf_path), media_type="application/pdf", filename=f"proposal-{p.id}.pdf")


# --- Vista interna (equipo) --------------------------------------------------------------------


@router.get("/{lead_id}/internal/messages", dependencies=[AdminOnly])
async def internal_messages(lead_id: int, session: AsyncSession = Session) -> list[MessageInternal]:
    rows = (
        await session.scalars(select(Message).where(Message.lead_id == lead_id).order_by(Message.id))
    ).all()
    return [MessageInternal.model_validate(m) for m in rows]


@router.get("/{lead_id}/internal/qualification", dependencies=[AdminOnly])
async def internal_qualification(lead_id: int, session: AsyncSession = Session) -> dict[str, Any]:
    lead = await get_lead(session, lead_id)
    return lead.qualification_detail or {}


@router.get("/{lead_id}/internal/estimate", dependencies=[AdminOnly])
async def internal_estimate(lead_id: int, session: AsyncSession = Session) -> dict[str, Any]:
    est = await session.scalar(
        select(Estimate).where(Estimate.lead_id == lead_id).order_by(Estimate.id.desc())
    )
    if est is None:
        raise HTTPException(404, "no estimate")
    return {"id": est.id, "status": est.status, "error": est.error, "result": est.result}
