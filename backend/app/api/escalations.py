from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminOnly
from app.core.db import get_session
from app.models import Escalation, Lead, Message

router = APIRouter(prefix="/api/escalations", tags=["escalations"], dependencies=[AdminOnly])
Session = Depends(get_session)


class EscalationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    lead_id: int
    lead_name: str = ""
    reason: str
    client_request: str
    summary: str
    violations: list[dict[str, Any]]
    status: str
    resolution: str | None
    created_at: datetime


@router.get("")
async def list_escalations(status: str | None = None, session: AsyncSession = Session) -> list[EscalationOut]:
    stmt = (
        select(Escalation, Lead.name).join(Lead, Lead.id == Escalation.lead_id).order_by(Escalation.id.desc())
    )
    if status:
        stmt = stmt.where(Escalation.status == status)
    rows = (await session.execute(stmt)).all()
    return [EscalationOut.model_validate(e).model_copy(update={"lead_name": name}) for e, name in rows]


class ResolveIn(BaseModel):
    reply_to_client: str = Field(min_length=1, description="What the team member replies to the client")


@router.post("/{escalation_id}/resolve")
async def resolve(escalation_id: int, data: ResolveIn, session: AsyncSession = Session) -> EscalationOut:
    esc = await session.get(Escalation, escalation_id)
    if esc is None:
        raise HTTPException(404, "escalation not found")
    if esc.status == "resolved":
        raise HTTPException(409, "already resolved")
    esc.status, esc.resolution = "resolved", data.reply_to_client
    session.add(
        Message(
            lead_id=esc.lead_id,
            role="human",
            agent="human",
            content=data.reply_to_client,
            meta={"escalation_id": esc.id},
        )
    )
    await session.commit()
    lead = await session.get(Lead, esc.lead_id)
    return EscalationOut.model_validate(esc).model_copy(update={"lead_name": lead.name})
