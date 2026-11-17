"""Enruta cada mensaje del cliente al agente de su etapa y deja el turno trazado y persistido."""

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import commercial, qualification, requirements
from app.agents.base import AgentContext, AgentReply, Emit, TurnLog, _no_emit
from app.core.llm import LLMClient
from app.core.telemetry import set_json_attr, tracer
from app.models import Lead, Message, Stage

AGENTS: dict[str, Callable[[AgentContext], Awaitable[AgentReply]]] = {
    Stage.qualification: qualification.handle,
    Stage.requirements: requirements.handle,
    Stage.commercial: commercial.handle,
}

IDLE_REPLIES = {
    Stage.estimating: "The team is preparing your project estimate. I'll message you as soon as it's ready.",
    Stage.nurture: "Thanks! We've taken note and will get in touch when we can help.",
    Stage.discarded: "Thanks for reaching out. If your situation changes, we'd be happy to talk.",
    Stage.closed: "Your proposal is already closed. If you need anything else, the team will contact you.",
}


def trace_id_hex(span) -> str:
    return format(span.get_span_context().trace_id, "032x")


async def handle_message(
    session: AsyncSession, llm: LLMClient, lead: Lead, content: str, emit: Emit = _no_emit
) -> Message:
    with tracer.start_as_current_span("conversation.turn") as span:
        span.set_attribute("conversation.id", lead.id)
        span.set_attribute("conversation.stage", lead.stage)
        session.add(Message(lead_id=lead.id, role="user", content=content))
        await session.flush()

        ctx = AgentContext(session=session, llm=llm, lead=lead, emit=emit)
        handler = AGENTS.get(lead.stage)
        if handler:
            reply = await handler(ctx)
        else:
            reply = AgentReply(content=IDLE_REPLIES[lead.stage], agent="system", log=TurnLog())

        meta = reply.log.as_meta() | {"trace_id": trace_id_hex(span)}
        span.set_attribute("agent.name", reply.agent)
        set_json_attr(span, "agent.rules", reply.log.rules)
        set_json_attr(span, "agent.violations", reply.log.violations)
        set_json_attr(span, "agent.tool_calls", reply.log.tool_calls)
        span.set_attribute("agent.violation_count", len(reply.log.violations))

        msg = Message(lead_id=lead.id, role="assistant", agent=reply.agent, content=reply.content, meta=meta)
        session.add(msg)
        await session.commit()
        for effect in ctx.after_commit:
            effect()
        return msg
