import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import LLMClient, tool_spec
from app.core.telemetry import set_json_attr, tracer
from app.models import Lead, Message

Emit = Callable[[str, Any], Awaitable[None]]


async def _no_emit(event: str, data: Any) -> None:
    return None


@dataclass
class AgentContext:
    session: AsyncSession
    llm: LLMClient
    lead: Lead
    emit: Emit = _no_emit
    # Efectos que solo deben ocurrir si el turno se guarda (p. ej. encolar tareas Celery)
    after_commit: list[Callable[[], None]] = field(default_factory=list)


@dataclass
class TurnLog:
    """Lo que se guarda en el mensaje y en la traza: herramientas usadas y reglas aplicadas."""

    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    violations: list[dict[str, Any]] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)

    def as_meta(self) -> dict[str, Any]:
        return {
            "tool_calls": self.tool_calls,
            "rules": self.rules,
            "violations": self.violations,
            "citations": self.citations,
        }


@dataclass
class AgentReply:
    content: str
    agent: str
    log: TurnLog


@dataclass
class Tool:
    name: str
    description: str
    args: type[BaseModel]
    handler: Callable[[Any], Awaitable[Any]]

    def spec(self) -> dict:
        return tool_spec(self.name, self.description, self.args)


async def history(session: AsyncSession, lead_id: int, with_ids: bool = False) -> list[dict[str, Any]]:
    rows = (
        await session.scalars(select(Message).where(Message.lead_id == lead_id).order_by(Message.id))
    ).all()
    out = []
    for m in rows:
        role = "user" if m.role == "user" else "assistant"
        content = f"[msg {m.id}] {m.content}" if with_ids and m.role == "user" else m.content
        out.append({"role": role, "content": content})
    return out


async def run_tool_loop(
    llm: LLMClient, messages: list[dict[str, Any]], tools: list[Tool], log: TurnLog, max_steps: int = 8
) -> str:
    by_name = {t.name: t for t in tools}
    specs = [t.spec() for t in tools]
    for _ in range(max_steps):
        resp = await llm.chat(messages, specs)
        if not resp.tool_calls:
            return resp.content or ""
        messages.append(
            {
                "role": "assistant",
                "content": resp.content,
                "tool_calls": [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {
                            "name": c.name,
                            "arguments": json.dumps(c.arguments, ensure_ascii=False),
                        },
                    }
                    for c in resp.tool_calls
                ],
            }
        )
        for call in resp.tool_calls:
            with tracer.start_as_current_span(f"tool.{call.name}") as span:
                set_json_attr(span, "tool.args", call.arguments)
                tool = by_name.get(call.name)
                if tool is None:
                    result: Any = {"error": f"unknown tool: {call.name}"}
                else:
                    try:
                        result = await tool.handler(tool.args.model_validate(call.arguments))
                    except ValidationError as e:
                        result = {"error": f"invalid arguments: {e.errors(include_url=False)}"}
                set_json_attr(span, "tool.result", result)
            log.tool_calls.append({"name": call.name, "args": call.arguments})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": call.name,
                    "content": json.dumps(result, default=str, ensure_ascii=False),
                }
            )
    # Demasiados pasos: pedimos una respuesta final sin herramientas
    resp = await llm.chat(messages)
    return resp.content or ""
