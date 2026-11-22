"""Documentación de cada proyecto: la lógica de negocio acordada con el cliente y las páginas del equipo.

El acuerdo se genera a partir de la última versión confirmada de los requisitos (la fuente de verdad) y no se
edita a mano: cambia solo cuando el cliente confirma una versión nueva.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, Lead, RequirementVersion
from app.rag.guides import content_hash
from app.schemas.requirements import AmbiguityStatus, RequirementDoc

PROJECT = "project"
AGREEMENT = "agreement"
PAGE = "page"


def agreement_markdown(doc: RequirementDoc, version: RequirementVersion, project: str) -> str:
    lines = [
        f"# Business agreement: {project}",
        "",
        f"Generated from requirements version {version.version}, confirmed by the client on "
        f"{version.confirmed_at:%B %d, %Y} (SHA-256 `{version.sha256[:12]}`). "
        "This page is the source of truth for what was agreed and updates automatically with every new version.",
        "",
        "## Summary",
        "",
        doc.summary or "No summary.",
    ]
    for epic in doc.epics:
        lines += ["", f"## {epic.id}: {epic.title}", ""]
        if epic.description:
            lines += [epic.description, ""]
        for s in (s for s in doc.stories if s.epic_id == epic.id):
            story = f"As {s.as_a}, I want {s.i_want}" + (f" so that {s.so_that}" if s.so_that else "") + "."
            lines += [f"### {s.id}", "", story, ""]
            if s.acceptance_criteria:
                lines += ["Acceptance criteria:", "", *[f"- {ac}" for ac in s.acceptance_criteria], ""]
    if doc.nfrs:
        lines += [
            "",
            "## Non-functional requirements",
            "",
            "| Id | Category | Requirement |",
            "|---|---|---|",
        ]
        lines += [f"| {n.id} | {n.category} | {n.text} |" for n in doc.nfrs]
    if doc.out_of_scope:
        lines += ["", "## Out of scope", "", *[f"- {o}" for o in doc.out_of_scope]]
    decisions = [a for a in doc.ambiguities if a.status == AmbiguityStatus.resolved and a.resolution]
    if decisions:
        lines += [
            "",
            "## Decisions",
            "",
            "Questions raised while gathering requirements and how the client resolved them.",
            "",
        ]
        lines += [f"- **{a.question}** {a.resolution}" for a in decisions]
    return "\n".join(lines).strip() + "\n"


async def is_project(session: AsyncSession, lead_id: int) -> bool:
    """Un lead es un proyecto cuando el cliente ha confirmado al menos una versión de requisitos."""
    return bool(
        await session.scalar(
            select(RequirementVersion.id).where(RequirementVersion.lead_id == lead_id).limit(1)
        )
    )


async def ensure_agreement(session: AsyncSession, lead_id: int) -> Document | None:
    """Crea o actualiza la página del acuerdo. Devuelve el documento si hay que (re)indexarlo."""
    version = await session.scalar(
        select(RequirementVersion)
        .where(RequirementVersion.lead_id == lead_id)
        .order_by(RequirementVersion.version.desc())
        .limit(1)
    )
    if version is None:
        return None
    lead = await session.get(Lead, lead_id)
    text = agreement_markdown(RequirementDoc.model_validate(version.doc), version, lead.name)
    digest = content_hash(text)
    doc = await session.scalar(
        select(Document).where(Document.lead_id == lead_id, Document.source == AGREEMENT)
    )
    if doc is not None and doc.content_hash == digest and doc.status == "ready":
        return None
    if doc is None:
        doc = Document(kind=PROJECT, source=AGREEMENT, lead_id=lead_id, filename="agreement.md", path="")
        session.add(doc)
    doc.title = "Business agreement"
    doc.content, doc.content_hash, doc.status = text, digest, "pending"
    await session.flush()
    return doc
