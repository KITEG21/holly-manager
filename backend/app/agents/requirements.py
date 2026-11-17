"""Agente de requisitos: conversa con el cliente y rellena en vivo un documento estructurado."""

import json

from pydantic import BaseModel, Field

from app.agents.base import AgentContext, AgentReply, Tool, TurnLog, history, run_tool_loop
from app.core.config import get_settings
from app.models import RequirementDraft
from app.schemas.requirements import NFR, Ambiguity, AmbiguityStatus, Epic, RequirementDoc, UserStory

SYSTEM_PROMPT = """You are the requirements analyst at {company}. You are talking to an already qualified client.
Your goal is to build a complete, unambiguous requirements document using the tools.

How you work:
- Every time the client provides information, record it with the tools (epics, user stories with testable
  acceptance criteria, non-functional requirements, out of scope).
- In source_message_ids, list the [msg N] ids of the client messages each story or requirement comes from.
- If you detect something ambiguous or a contradiction with what is already recorded, call flag_ambiguity and
  ask about it BEFORE moving on. When the client clarifies, call resolve_ambiguity and update what is affected.
- Ask at most two questions per message. Write everything (replies and the document) in English.
- Never talk about prices, hours, delivery dates or discounts: the team calculates that later.
- When the document is complete, call propose_summary with a clear summary. If the tool returns problems,
  fix them. If it accepts it, present the summary and ask the client to review it and click
  "Confirm agreement".

Current document:
{doc}"""


class EpicArgs(BaseModel):
    id: str = Field(description="E-1, E-2...")
    title: str
    description: str = ""


class StoryArgs(BaseModel):
    id: str = Field(description="US-1, US-2...")
    epic_id: str
    as_a: str
    i_want: str
    so_that: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    source_message_ids: list[int] = Field(default_factory=list)


class NFRArgs(BaseModel):
    id: str = Field(description="NFR-1, NFR-2...")
    category: str = Field(description="performance, security, accessibility, availability, legal...")
    text: str
    source_message_ids: list[int] = Field(default_factory=list)


class OutOfScopeArgs(BaseModel):
    item: str


class AmbiguityArgs(BaseModel):
    question: str


class ResolveArgs(BaseModel):
    id: str
    resolution: str


class SummaryArgs(BaseModel):
    summary: str


def _upsert(items: list, new) -> None:
    for i, item in enumerate(items):
        if item.id == new.id:
            items[i] = new
            return
    items.append(new)


def build_tools(doc: RequirementDoc) -> list[Tool]:
    async def upsert_epic(a: EpicArgs):
        _upsert(doc.epics, Epic(**a.model_dump()))
        return {"ok": True}

    async def upsert_story(a: StoryArgs):
        if a.epic_id not in {e.id for e in doc.epics}:
            return {"error": f"epic {a.epic_id} does not exist; create it first with upsert_epic"}
        _upsert(doc.stories, UserStory(**a.model_dump()))
        doc.summary = None  # cualquier cambio invalida el resumen propuesto
        return {"ok": True}

    async def add_nfr(a: NFRArgs):
        _upsert(doc.nfrs, NFR(**a.model_dump()))
        doc.summary = None
        return {"ok": True}

    async def add_out_of_scope(a: OutOfScopeArgs):
        if a.item not in doc.out_of_scope:
            doc.out_of_scope.append(a.item)
        return {"ok": True}

    async def flag_ambiguity(a: AmbiguityArgs):
        amb = Ambiguity(id=f"A-{len(doc.ambiguities) + 1}", question=a.question)
        doc.ambiguities.append(amb)
        doc.summary = None
        return {"ok": True, "id": amb.id}

    async def resolve_ambiguity(a: ResolveArgs):
        for amb in doc.ambiguities:
            if amb.id == a.id:
                amb.status = AmbiguityStatus.resolved
                amb.resolution = a.resolution
                return {"ok": True}
        return {"error": f"ambiguity {a.id} does not exist"}

    async def propose_summary(a: SummaryArgs):
        doc.summary = a.summary
        problems = doc.readiness_problems()
        if problems:
            doc.summary = None
            return {"accepted": False, "problems": problems}
        return {"accepted": True}

    return [
        Tool("upsert_epic", "Create or update an epic.", EpicArgs, upsert_epic),
        Tool("upsert_story", "Create or update a user story.", StoryArgs, upsert_story),
        Tool("add_nfr", "Create or update a non-functional requirement.", NFRArgs, add_nfr),
        Tool(
            "add_out_of_scope",
            "Record something that is explicitly out of scope.",
            OutOfScopeArgs,
            add_out_of_scope,
        ),
        Tool(
            "flag_ambiguity",
            "Record an ambiguity or contradiction that must be asked about.",
            AmbiguityArgs,
            flag_ambiguity,
        ),
        Tool("resolve_ambiguity", "Mark an ambiguity as resolved.", ResolveArgs, resolve_ambiguity),
        Tool(
            "propose_summary",
            "Propose the final summary; validates that the document is complete.",
            SummaryArgs,
            propose_summary,
        ),
    ]


async def load_draft(ctx: AgentContext) -> tuple[RequirementDraft, RequirementDoc]:
    draft = await ctx.session.get(RequirementDraft, ctx.lead.id)
    if draft is None:
        draft = RequirementDraft(lead_id=ctx.lead.id, doc=RequirementDoc().model_dump(mode="json"))
        ctx.session.add(draft)
    return draft, RequirementDoc.model_validate(draft.doc)


async def handle(ctx: AgentContext) -> AgentReply:
    log = TurnLog()
    draft, doc = await load_draft(ctx)
    tools = build_tools(doc)
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT.format(
                doc=json.dumps(doc.model_dump(mode="json"), ensure_ascii=False),
                company=get_settings().company_name,
            ),
        },
        *await history(ctx.session, ctx.lead.id, with_ids=True),
    ]
    content = await run_tool_loop(ctx.llm, messages, tools, log)
    draft.doc = doc.model_dump(mode="json")
    log.rules.append(f"requirements.readiness={doc.readiness_problems() or 'ok'}")
    await ctx.emit("draft", draft.doc)
    return AgentReply(content=content, agent="requirements", log=log)
