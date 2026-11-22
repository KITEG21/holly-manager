import asyncio

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import task_session
from app.core.llm import LiteLLMClient
from app.models import Document, HistoricalTask
from app.rag.guides import index_guide, ingest_upload, sync_builtin
from app.rag.ingest import ingest_document
from app.rag.project_docs import ensure_agreement
from app.worker import celery_app


@celery_app.task(name="ingest_document")
def ingest_document_task(document_id: int) -> int:
    async def _run() -> int:
        async with task_session() as session:
            doc = await session.get(Document, document_id)
            try:
                count = await ingest_document(session, LiteLLMClient(), doc)
                doc.status, doc.chunk_count, doc.error = "ready", count, None
            except Exception as e:  # noqa: BLE001
                await session.rollback()
                doc = await session.get(Document, document_id)
                doc.status, doc.error = "failed", str(e)[:2000]
                count = 0
            await session.commit()
            return count

    return asyncio.run(_run())


@celery_app.task(name="embed_historical")
def embed_historical_task() -> int:
    async def _run() -> int:
        async with task_session() as session:
            rows = (
                await session.scalars(select(HistoricalTask).where(HistoricalTask.embedding.is_(None)))
            ).all()
            if rows:
                vectors = await LiteLLMClient().embed([r.title for r in rows])
                for row, vec in zip(rows, vectors, strict=True):
                    row.embedding = vec
                await session.commit()
            return len(rows)

    return asyncio.run(_run())


@celery_app.task(name="ingest_guide")
def ingest_guide_task(document_id: int) -> int:
    async def _run() -> int:
        async with task_session() as session:
            doc = await session.get(Document, document_id)
            try:
                count = await ingest_upload(session, LiteLLMClient(), doc)
            except Exception as e:  # noqa: BLE001
                await session.rollback()
                doc = await session.get(Document, document_id)
                doc.status, doc.error = "failed", str(e)[:2000]
                count = 0
            await session.commit()
            return count

    return asyncio.run(_run())


@celery_app.task(name="sync_builtin_docs")
def sync_builtin_docs_task() -> dict[str, int]:
    async def _run() -> dict[str, int]:
        async with task_session() as session:
            return await sync_builtin(session, LiteLLMClient(), get_settings().docs_dir)

    return asyncio.run(_run())


@celery_app.task(name="sync_agreement_doc")
def sync_agreement_doc_task(lead_id: int) -> int:
    """Genera (o actualiza) la página del acuerdo de un proyecto y la indexa."""

    async def _run() -> int:
        async with task_session() as session:
            doc = await ensure_agreement(session, lead_id)
            if doc is None:
                await session.commit()
                return 0
            count = await index_guide(session, LiteLLMClient(), doc)
            await session.commit()
            return count

    return asyncio.run(_run())
