"""Ingesta de documentos con Docling: estructura (secciones, páginas) → chunks → embeddings → pgvector."""

from pathlib import Path
from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import LLMClient
from app.core.telemetry import tracer
from app.models import Document, DocumentChunk

EMBED_BATCH = 32


def parse_with_docling(path: Path) -> list[dict[str, Any]]:
    # Import diferido: Docling es pesado y solo está en la imagen del worker
    from docling.chunking import HybridChunker
    from docling.document_converter import DocumentConverter

    doc = DocumentConverter().convert(path).document
    chunker = HybridChunker()
    chunks = []
    for chunk in chunker.chunk(doc):
        meta = chunk.meta
        headings = getattr(meta, "headings", None) or []
        page = None
        for item in getattr(meta, "doc_items", []) or []:
            for prov in getattr(item, "prov", []) or []:
                page = prov.page_no
                break
            if page:
                break
        chunks.append(
            {
                "text": chunker.contextualize(chunk),
                "section": " > ".join(headings) if headings else None,
                "page": page,
            }
        )
    return chunks


async def ingest_document(session: AsyncSession, llm: LLMClient, document: Document) -> int:
    with tracer.start_as_current_span("rag.ingest") as span:
        span.set_attribute("document.id", document.id)
        span.set_attribute("document.filename", document.filename)
        parsed = [c for c in parse_with_docling(Path(document.path)) if c["text"].strip()]
        await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
        for start in range(0, len(parsed), EMBED_BATCH):
            batch = parsed[start : start + EMBED_BATCH]
            vectors = await llm.embed([c["text"] for c in batch])
            session.add_all(
                DocumentChunk(
                    document_id=document.id,
                    kind=document.kind,
                    content=c["text"],
                    meta={"source": document.filename, "section": c["section"], "page": c["page"]},
                    embedding=vec,
                )
                for c, vec in zip(batch, vectors, strict=True)
            )
        span.set_attribute("document.chunks", len(parsed))
        return len(parsed)
