"""Asistente de documentación: responde a desarrolladores y admins solo con lo que dice la documentación.

Igual que el agente comercial, la respuesta pasa por `check_citations`: sin citas válidas no llega al usuario.
"""

import re

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.llm import LLMClient
from app.core.telemetry import set_json_attr, tracer
from app.domain.guardrails import check_citations, cited_ids
from app.rag.guides import GUIDE
from app.rag.retrieve import Citation, search_documents

TOP_K = 6
NOT_FOUND = "NOT_FOUND"

SYSTEM_PROMPT = """You are the documentation assistant for {scope}. You answer questions from
developers and admins using ONLY the documentation excerpts below.

Rules:
- Every statement must be backed by an excerpt and cite it with its marker, e.g. [C1] or [C2][C3].
- Do not use outside knowledge and do not guess numbers, rules or behaviour that the excerpts don't state.
- If the excerpts don't contain the answer, reply with exactly: {not_found}
- Be concise and practical. Use short paragraphs or bullet lists. Reply in English.

Documentation excerpts:
{excerpts}"""

NOT_FOUND_REPLY = "I couldn't find that in the documentation."
UNGROUNDED_REPLY = (
    "I couldn't give a reliable answer based on the documentation. These sections look related:"
)


class Turn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=8000)


class DocsCitation(BaseModel):
    id: int
    document_id: int
    title: str
    section: str | None
    label: str


class DocsAnswer(BaseModel):
    answer: str
    grounded: bool  # False: no se encontró respaldo en la documentación
    citations: list[DocsCitation]


def _to_citation(c: Citation) -> DocsCitation:
    return DocsCitation(id=c.id, document_id=c.document_id, title=c.source, section=c.section, label=c.label)


def _related(found: list[Citation]) -> list[DocsCitation]:
    """Una sugerencia por sección, en orden de relevancia."""
    seen, out = set(), []
    for c in found:
        key = (c.document_id, c.section)
        if key not in seen:
            seen.add(key)
            out.append(_to_citation(c))
    return out[:3]


_FOLLOW_UP = re.compile(
    r"^(and|or|but|also|so|then|what about|how about|what if|why)\b|\b(it|its|that|this|those|these|they|them)\b",
    re.IGNORECASE,
)


def retrieval_query(question: str, history: list[Turn]) -> str:
    # Una pregunta de seguimiento ("and what if…?", "why is that?") necesita el contexto de la anterior;
    # una pregunta corta pero independiente no, o la búsqueda arrastraría el tema anterior
    previous = [t.content for t in history if t.role == "user"]
    if previous and len(question.split()) < 12 and _FOLLOW_UP.search(question):
        return f"{previous[-1]} {question}"
    return question


async def answer_question(
    session: AsyncSession,
    llm: LLMClient,
    question: str,
    history: list[Turn],
    *,
    kinds: tuple[str, ...] = (GUIDE,),
    lead_id: int | None = None,
    scope: str | None = None,
) -> DocsAnswer:
    """Sin `lead_id` responde con la documentación del sistema; con él, solo con la de ese proyecto."""
    with tracer.start_as_current_span("docs.ask") as span:
        span.set_attribute("docs.question", question[:500])
        span.set_attribute("docs.lead_id", lead_id or 0)
        found = await search_documents(
            session, llm, retrieval_query(question, history), list(kinds), k=TOP_K, lead_id=lead_id
        )
        set_json_attr(span, "docs.sources", [c.label for c in found])
        if not found:
            return DocsAnswer(answer="There is no documentation indexed yet.", grounded=False, citations=[])

        excerpts = "\n\n".join(f"[C{c.id}] ({c.label})\n{c.text}" for c in found)
        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT.format(
                    scope=scope or f"{get_settings().company_name}'s internal platform",
                    not_found=NOT_FOUND,
                    excerpts=excerpts,
                ),
            },
            *[t.model_dump() for t in history[-6:]],
            {"role": "user", "content": question},
        ]
        valid_ids = {c.id for c in found}
        for attempt in range(2):
            text = ((await llm.chat(messages)).content or "").strip()
            if text.startswith(NOT_FOUND):
                span.set_attribute("docs.outcome", "not_found")
                # Si la documentación no lo cubre, sugerir secciones al azar confunde más que ayuda
                return DocsAnswer(answer=NOT_FOUND_REPLY, grounded=False, citations=[])
            violations = check_citations(text, valid_ids)
            if not violations:
                cited = cited_ids(text)
                span.set_attribute("docs.outcome", f"answered[{attempt}]")
                return DocsAnswer(
                    answer=text, grounded=True, citations=[_to_citation(c) for c in found if c.id in cited]
                )
            messages += [
                {"role": "assistant", "content": text},
                {
                    "role": "user",
                    "content": "Your answer was rejected: cite every statement with the excerpt markers "
                    f"(for example [C1]), or reply with exactly {NOT_FOUND} if the excerpts don't answer it.",
                },
            ]
        span.set_attribute("docs.outcome", "ungrounded")
        return DocsAnswer(answer=UNGROUNDED_REPLY, grounded=False, citations=_related(found))
