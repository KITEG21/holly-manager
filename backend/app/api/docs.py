"""Documentación para el equipo: consulta, asistente con citas y gestión de documentos (solo admins)."""

import shutil
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.docs_assistant import DocsAnswer, Turn, answer_question
from app.api.deps import AdminOnly, TeamOnly
from app.core.config import get_settings
from app.core.db import get_session
from app.core.llm import get_llm
from app.models import Document
from app.rag.guides import GUIDE, UPLOAD_SUFFIXES

router = APIRouter(prefix="/api/docs", tags=["docs"], dependencies=[TeamOnly])
Session = Depends(get_session)


class DocOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    slug: str | None
    title: str | None
    filename: str
    source: str
    status: str
    error: str | None
    chunk_count: int
    created_at: datetime
    updated_at: datetime | None = None


class DocDetail(DocOut):
    content: str | None


async def _get_guide(session: AsyncSession, doc_id: int) -> Document:
    doc = await session.get(Document, doc_id)
    if doc is None or doc.kind != GUIDE:
        raise HTTPException(404, "document not found")
    return doc


@router.get("")
async def list_docs(session: AsyncSession = Session) -> list[DocOut]:
    # Primero los del repositorio, en su orden (01-, 02-…); después los subidos, por título
    rows = (
        await session.scalars(
            select(Document)
            .where(Document.kind == GUIDE)
            .order_by(case((Document.source == "builtin", 0), else_=1), Document.filename, Document.title)
        )
    ).all()
    return [DocOut.model_validate(d) for d in rows]


@router.get("/{doc_id}")
async def get_doc(doc_id: int, session: AsyncSession = Session) -> DocDetail:
    return DocDetail.model_validate(await _get_guide(session, doc_id))


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[Turn] = Field(default_factory=list, max_length=20)


@router.post("/ask")
async def ask(data: AskIn, session: AsyncSession = Session) -> DocsAnswer:
    return await answer_question(session, get_llm(), data.question, data.history)


@router.post("", dependencies=[AdminOnly])
async def upload_doc(file: UploadFile = File(...), session: AsyncSession = Session) -> DocOut:
    from app.tasks.ingest import ingest_guide_task

    name = file.filename or "document"
    suffix = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if suffix not in UPLOAD_SUFFIXES:
        allowed = ", ".join(sorted(UPLOAD_SUFFIXES))
        raise HTTPException(422, f"unsupported format: {suffix or 'no extension'} (allowed: {allowed})")
    folder = get_settings().storage_dir / "guides"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex}{suffix}"
    with path.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    doc = Document(filename=name, kind=GUIDE, source="upload", path=str(path), title=name.rsplit(".", 1)[0])
    session.add(doc)
    await session.commit()
    ingest_guide_task.delay(doc.id)
    return DocOut.model_validate(doc)


@router.delete("/{doc_id}", dependencies=[AdminOnly])
async def delete_doc(doc_id: int, session: AsyncSession = Session) -> dict[str, bool]:
    doc = await _get_guide(session, doc_id)
    if doc.source == "builtin":
        raise HTTPException(409, "built-in documents are maintained in the repository (backend/docs)")
    await session.delete(doc)
    await session.commit()
    return {"deleted": True}


@router.post("/sync", dependencies=[AdminOnly])
async def sync_docs() -> dict[str, str]:
    from app.tasks.ingest import sync_builtin_docs_task

    sync_builtin_docs_task.delay()
    return {"status": "queued"}
