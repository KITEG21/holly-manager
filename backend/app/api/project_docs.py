"""Documentación de cada proyecto: acuerdo de negocio generado, páginas del equipo, archivos y asistente propio."""

import logging
import shutil
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.docs_assistant import DocsAnswer, answer_question
from app.api.deps import TeamOnly
from app.api.docs import AskIn, DocDetail, DocOut
from app.core.config import get_settings
from app.core.db import get_session
from app.core.llm import get_llm
from app.models import Document, Lead
from app.rag.guides import UPLOAD_SUFFIXES, content_hash, index_guide
from app.rag.project_docs import AGREEMENT, PAGE, PROJECT, ensure_agreement, is_project

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/projects/{lead_id}/docs", tags=["project docs"], dependencies=[TeamOnly])
Session = Depends(get_session)


async def _project(session: AsyncSession, lead_id: int) -> Lead:
    lead = await session.get(Lead, lead_id)
    if lead is None or not await is_project(session, lead_id):
        raise HTTPException(404, "project not found")
    return lead


async def _doc(session: AsyncSession, lead_id: int, doc_id: int) -> Document:
    doc = await session.get(Document, doc_id)
    if doc is None or doc.kind != PROJECT or doc.lead_id != lead_id:
        raise HTTPException(404, "document not found")
    return doc


def _enqueue_agreement(lead_id: int) -> None:
    from app.tasks.ingest import sync_agreement_doc_task

    try:
        sync_agreement_doc_task.delay(lead_id)
    except Exception:  # noqa: BLE001  se reintenta en la siguiente visita
        log.exception("could not enqueue sync_agreement_doc")


@router.get("")
async def list_project_docs(lead_id: int, session: AsyncSession = Session) -> list[DocOut]:
    await _project(session, lead_id)
    # Los proyectos confirmados antes de existir esta sección obtienen su acuerdo en la primera visita
    if await ensure_agreement(session, lead_id) is not None:
        await session.commit()
        _enqueue_agreement(lead_id)
    rows = (
        await session.scalars(
            select(Document)
            .where(Document.kind == PROJECT, Document.lead_id == lead_id)
            .order_by(case((Document.source == AGREEMENT, 0), else_=1), Document.title)
        )
    ).all()
    return [DocOut.model_validate(d) for d in rows]


@router.get("/{doc_id}")
async def get_project_doc(lead_id: int, doc_id: int, session: AsyncSession = Session) -> DocDetail:
    return DocDetail.model_validate(await _doc(session, lead_id, doc_id))


class PageIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=200_000)


async def _save_page(session: AsyncSession, doc: Document, data: PageIn) -> DocDetail:
    doc.title, doc.content, doc.content_hash = data.title.strip(), data.content, content_hash(data.content)
    await session.flush()
    try:
        await index_guide(session, get_llm(), doc)
    except Exception as e:  # noqa: BLE001  la página se guarda aunque falle la indexación
        doc.status, doc.error = "failed", f"could not index the page: {e}"[:2000]
    await session.commit()
    return DocDetail.model_validate(doc)


@router.post("")
async def create_page(lead_id: int, data: PageIn, session: AsyncSession = Session) -> DocDetail:
    await _project(session, lead_id)
    doc = Document(kind=PROJECT, source=PAGE, lead_id=lead_id, filename="page.md", path="")
    session.add(doc)
    return await _save_page(session, doc, data)


@router.put("/{doc_id}")
async def update_page(lead_id: int, doc_id: int, data: PageIn, session: AsyncSession = Session) -> DocDetail:
    doc = await _doc(session, lead_id, doc_id)
    if doc.source != PAGE:
        raise HTTPException(409, "only pages written in the app can be edited")
    return await _save_page(session, doc, data)


@router.post("/upload")
async def upload_project_doc(
    lead_id: int, file: UploadFile = File(...), session: AsyncSession = Session
) -> DocOut:
    from app.tasks.ingest import ingest_guide_task

    await _project(session, lead_id)
    name = file.filename or "document"
    suffix = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if suffix not in UPLOAD_SUFFIXES:
        allowed = ", ".join(sorted(UPLOAD_SUFFIXES))
        raise HTTPException(422, f"unsupported format: {suffix or 'no extension'} (allowed: {allowed})")
    folder = get_settings().storage_dir / "projects" / str(lead_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex}{suffix}"
    with path.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    doc = Document(
        kind=PROJECT,
        source="upload",
        lead_id=lead_id,
        filename=name,
        path=str(path),
        title=name.rsplit(".", 1)[0],
    )
    session.add(doc)
    await session.commit()
    ingest_guide_task.delay(doc.id)
    return DocOut.model_validate(doc)


@router.delete("/{doc_id}")
async def delete_project_doc(lead_id: int, doc_id: int, session: AsyncSession = Session) -> dict[str, bool]:
    doc = await _doc(session, lead_id, doc_id)
    if doc.source == AGREEMENT:
        raise HTTPException(409, "the business agreement is generated from the confirmed requirements")
    await session.delete(doc)
    await session.commit()
    return {"deleted": True}


@router.post("/ask")
async def ask_project_docs(lead_id: int, data: AskIn, session: AsyncSession = Session) -> DocsAnswer:
    lead = await _project(session, lead_id)
    return await answer_question(
        session,
        get_llm(),
        data.question,
        data.history,
        kinds=(PROJECT,),
        lead_id=lead_id,
        scope=f'the project "{lead.name}" (its agreed business logic and the team\'s notes)',
    )
