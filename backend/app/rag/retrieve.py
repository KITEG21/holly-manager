from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import LLMClient
from app.core.telemetry import set_json_attr, tracer
from app.models import DocumentChunk, HistoricalTask
from app.schemas.estimation import HistoricalMatch


class Citation(BaseModel):
    id: int  # número que el agente usa en la respuesta: [C1], [C2]...
    chunk_id: int
    source: str
    section: str | None = None
    page: int | None = None
    text: str
    similarity: float

    @property
    def label(self) -> str:
        parts = [self.source]
        if self.section:
            parts.append(f"§ {self.section}")
        if self.page:
            parts.append(f"p. {self.page}")
        return " · ".join(parts)


async def search_documents(
    session: AsyncSession, llm: LLMClient, query: str, kinds: list[str], k: int = 4, start_id: int = 1
) -> list[Citation]:
    with tracer.start_as_current_span("rag.search_documents") as span:
        span.set_attribute("rag.query", query)
        [qvec] = await llm.embed([query], purpose="query")
        distance = DocumentChunk.embedding.cosine_distance(qvec)
        rows = (
            await session.execute(
                select(DocumentChunk, distance.label("d"))
                .where(DocumentChunk.kind.in_(kinds))
                .order_by(distance)
                .limit(k)
            )
        ).all()
        citations = [
            Citation(
                id=start_id + i,
                chunk_id=chunk.id,
                source=chunk.meta.get("source", "document"),
                section=chunk.meta.get("section"),
                page=chunk.meta.get("page"),
                text=chunk.content,
                similarity=round(1 - d, 3),
            )
            for i, (chunk, d) in enumerate(rows)
        ]
        set_json_attr(span, "rag.results", [c.model_dump(exclude={"text"}) for c in citations])
        return citations


async def similar_tasks(
    session: AsyncSession, llm: LLMClient, texts: list[str], task_types: list[str], k: int = 5
) -> list[list[HistoricalMatch]]:
    """Para cada tarea nueva, las k tareas históricas más parecidas del mismo tipo, con sus horas reales."""
    if not texts:
        return []
    with tracer.start_as_current_span("rag.similar_tasks") as span:
        span.set_attribute("rag.count", len(texts))
        vectors = await llm.embed(texts, purpose="query")
        out: list[list[HistoricalMatch]] = []
        for vec, task_type in zip(vectors, task_types, strict=True):
            distance = HistoricalTask.embedding.cosine_distance(vec)
            rows = (
                await session.execute(
                    select(HistoricalTask, distance.label("d"))
                    .where(HistoricalTask.task_type == task_type, HistoricalTask.embedding.is_not(None))
                    .order_by(distance)
                    .limit(k)
                )
            ).all()
            out.append(
                [
                    HistoricalMatch(
                        project=h.project,
                        title=h.title,
                        task_type=h.task_type,
                        actual_hours=h.actual_hours,
                        similarity=round(1 - d, 3),
                    )
                    for h, d in rows
                ]
            )
        return out
