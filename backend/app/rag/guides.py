"""Documentación del sistema: documentos incluidos en el repositorio (`backend/docs`) y documentos subidos por admins.

Todo se guarda como Markdown (para mostrarlo en la app) y se indexa por secciones en pgvector (kind="guide").
"""

import hashlib
import re
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import LLMClient
from app.core.telemetry import tracer
from app.models import Document, DocumentChunk
from app.rag.markdown import chunk_markdown, title_of

GUIDE = "guide"
EMBED_BATCH = 32
TEXT_SUFFIXES = {".md", ".markdown", ".txt"}
UPLOAD_SUFFIXES = TEXT_SUFFIXES | {".pdf", ".docx", ".html", ".pptx"}


def slug_for(path: Path) -> str:
    # 05-estimation.md -> estimation: el prefijo numérico solo fija el orden
    return re.sub(r"^\d+[-_]", "", path.stem).lower()


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


async def index_guide(session: AsyncSession, llm: LLMClient, doc: Document) -> int:
    """(Re)indexa un documento a partir de su Markdown. Devuelve el número de fragmentos."""
    with tracer.start_as_current_span("rag.index_guide") as span:
        span.set_attribute("document.id", doc.id)
        chunks = chunk_markdown(doc.content or "", doc.title or doc.filename)
        await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
        for start in range(0, len(chunks), EMBED_BATCH):
            batch = chunks[start : start + EMBED_BATCH]
            vectors = await llm.embed([c.text for c in batch], purpose="document")
            session.add_all(
                DocumentChunk(
                    document_id=doc.id,
                    kind=doc.kind,
                    content=c.text,
                    meta={"source": doc.title or doc.filename, "section": c.section, "page": None},
                    embedding=vec,
                )
                for c, vec in zip(batch, vectors, strict=True)
            )
        doc.status, doc.chunk_count, doc.error = "ready", len(chunks), None
        span.set_attribute("document.chunks", len(chunks))
        return len(chunks)


async def sync_builtin(session: AsyncSession, llm: LLMClient, docs_dir: Path) -> dict[str, int]:
    """Alinea la base de datos con los Markdown del repositorio. Solo reindexa lo que ha cambiado."""
    files = sorted(docs_dir.glob("*.md"))
    existing = {
        d.slug: d
        for d in (
            await session.scalars(
                select(Document).where(Document.kind == GUIDE, Document.source == "builtin")
            )
        ).all()
    }
    stats = {"added": 0, "updated": 0, "unchanged": 0, "removed": 0}
    seen = set()
    for path in files:
        slug = slug_for(path)
        seen.add(slug)
        text = path.read_text(encoding="utf-8")
        digest = content_hash(text)
        doc = existing.get(slug)
        if doc and doc.content_hash == digest and doc.status == "ready":
            stats["unchanged"] += 1
            continue
        if doc is None:
            doc = Document(kind=GUIDE, source="builtin", slug=slug, filename=path.name, path=str(path))
            session.add(doc)
            stats["added"] += 1
        else:
            stats["updated"] += 1
        doc.filename, doc.path = path.name, str(path)
        doc.title, doc.content, doc.content_hash = title_of(text, slug), text, digest
        await session.flush()
        await index_guide(session, llm, doc)
    for slug, doc in existing.items():
        if slug not in seen:
            await session.delete(doc)
            stats["removed"] += 1
    await session.commit()
    return stats


def to_markdown(path: Path) -> str:
    if path.suffix.lower() in TEXT_SUFFIXES:
        return path.read_text(encoding="utf-8", errors="replace")
    # Import diferido: Docling es pesado y solo está en la imagen del worker
    from docling.document_converter import DocumentConverter

    return DocumentConverter().convert(path).document.export_to_markdown()


async def ingest_upload(session: AsyncSession, llm: LLMClient, doc: Document) -> int:
    text = to_markdown(Path(doc.path))
    doc.content, doc.content_hash = text, content_hash(text)
    doc.title = title_of(
        text, Path(doc.filename).stem.replace("-", " ").replace("_", " ").strip().capitalize()
    )
    return await index_guide(session, llm, doc)
