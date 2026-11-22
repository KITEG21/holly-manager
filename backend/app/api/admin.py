import shutil
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminOnly
from app.core.config import get_settings
from app.core.db import get_session
from app.core.llm import get_llm
from app.models import Document, HistoricalTask, QualificationCriterion, TaskType
from app.repo import get_criteria, get_rules, get_task_types, get_team, get_thresholds, put_setting
from app.schemas.config import CommercialRules, QualificationThresholds, TaskTypeConfig, TeamConfig
from app.schemas.qualification import QualificationCriterionConfig

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[AdminOnly])
Session = Depends(get_session)


@router.get("/task-types")
async def list_task_types(session: AsyncSession = Session) -> list[TaskTypeConfig]:
    return list((await get_task_types(session)).values())


@router.put("/task-types")
async def replace_task_types(
    items: list[TaskTypeConfig], session: AsyncSession = Session
) -> list[TaskTypeConfig]:
    if len({i.name for i in items}) != len(items):
        raise HTTPException(422, "duplicate task type names")
    await session.execute(delete(TaskType))
    session.add_all(TaskType(**i.model_dump()) for i in items)
    await session.commit()
    return items


@router.get("/team")
async def read_team(session: AsyncSession = Session) -> TeamConfig:
    return await get_team(session)


@router.put("/team")
async def write_team(team: TeamConfig, session: AsyncSession = Session) -> TeamConfig:
    await put_setting(session, "team", team)
    await session.commit()
    return team


@router.get("/commercial")
async def read_commercial(session: AsyncSession = Session) -> CommercialRules:
    return await get_rules(session)


@router.put("/commercial")
async def write_commercial(rules: CommercialRules, session: AsyncSession = Session) -> CommercialRules:
    await put_setting(session, "commercial", rules)
    await session.commit()
    return rules


class QualificationConfig(BaseModel):
    thresholds: QualificationThresholds
    criteria: list[QualificationCriterionConfig]


@router.get("/qualification")
async def read_qualification(session: AsyncSession = Session) -> QualificationConfig:
    return QualificationConfig(thresholds=await get_thresholds(session), criteria=await get_criteria(session))


@router.put("/qualification")
async def write_qualification(
    cfg: QualificationConfig, session: AsyncSession = Session
) -> QualificationConfig:
    if len({c.key for c in cfg.criteria}) != len(cfg.criteria):
        raise HTTPException(422, "duplicate criteria")
    await put_setting(session, "qualification", cfg.thresholds)
    await session.execute(delete(QualificationCriterion))
    session.add_all(QualificationCriterion(**c.model_dump()) for c in cfg.criteria)
    await session.commit()
    return cfg


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    filename: str
    kind: str
    status: str
    error: str | None
    chunk_count: int


@router.get("/documents")
async def list_documents(session: AsyncSession = Session) -> list[DocumentOut]:
    rows = (await session.scalars(select(Document).order_by(Document.id.desc()))).all()
    return [DocumentOut.model_validate(r) for r in rows]


ALLOWED_SUFFIXES = {".pdf", ".docx", ".md", ".html", ".txt", ".pptx"}


@router.post("/documents")
async def upload_document(
    kind: str = Form(pattern="^(contract|policy)$"),
    file: UploadFile = File(...),
    session: AsyncSession = Session,
) -> DocumentOut:
    from app.tasks.ingest import ingest_document_task

    name = file.filename or "document"
    suffix = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(422, f"unsupported format: {suffix or 'no extension'}")
    folder = get_settings().storage_dir / "documents"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex}{suffix}"
    with path.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    doc = Document(filename=name, kind=kind, path=str(path))
    session.add(doc)
    await session.commit()
    ingest_document_task.delay(doc.id)
    return DocumentOut.model_validate(doc)


class HistoricalTaskIn(BaseModel):
    project: str
    title: str
    task_type: str
    estimated_hours: float | None = None
    actual_hours: float


class HistoricalStats(BaseModel):
    count: int
    embedded: int


@router.get("/historical")
async def historical_stats(session: AsyncSession = Session) -> HistoricalStats:
    count = await session.scalar(select(func.count(HistoricalTask.id)))
    embedded = await session.scalar(
        select(func.count(HistoricalTask.id)).where(HistoricalTask.embedding.is_not(None))
    )
    return HistoricalStats(count=count or 0, embedded=embedded or 0)


@router.post("/historical")
async def add_historical(items: list[HistoricalTaskIn], session: AsyncSession = Session) -> HistoricalStats:
    from app.tasks.ingest import embed_historical_task

    session.add_all(HistoricalTask(**i.model_dump()) for i in items)
    await session.commit()
    embed_historical_task.delay()
    return await historical_stats(session)


class LLMProviderStatus(BaseModel):
    name: str
    label: str
    model: str
    configured: bool
    position: int | None  # posición en la cadena de respaldo; None si no participa
    cooling_down_seconds: int


@router.get("/llm")
async def llm_status() -> list[LLMProviderStatus]:
    return [LLMProviderStatus(**p) for p in get_llm().status()]


@router.post("/llm/{name}/test")
async def llm_test(name: str) -> dict:
    llm = get_llm()
    if name not in {p["name"] for p in llm.status()}:
        raise HTTPException(404, "unknown provider")
    return await llm.ping(name)
