import asyncio

from sqlalchemy import select

from app.core.db import task_session
from app.core.llm import LiteLLMClient
from app.models import Document, HistoricalTask
from app.rag.ingest import ingest_document
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
