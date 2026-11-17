"""Agente comercial: negocia solo dentro de las reglas, cita el contrato y escala lo demás.

Defensa en capas:
1. El LLM no calcula precios: `propose_offer` recibe términos y el código construye y valida la oferta.
2. Una oferta inválida se registra y se escala automáticamente; el LLM recibe "escalated", no un "sí".
3. Antes de enviar, el texto pasa por `check_response_numbers` y, si consultó el contrato, `check_citations`.
   Si falla dos veces, se envía una respuesta segura fija y se escala.
"""

import json
from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.agents.base import AgentContext, AgentReply, Tool, TurnLog, history, run_tool_loop
from app.core.config import get_settings
from app.domain.guardrails import (
    allowed_numbers,
    build_offer,
    check_citations,
    check_response_numbers,
    numbers_in,
    validate_offer,
)
from app.domain.summary import client_safe_summary
from app.models import Escalation, Estimate, Offer, Proposal, RequirementVersion
from app.rag.retrieve import Citation, search_documents
from app.repo import get_rules
from app.schemas.commercial import ClientSafeSummary, CommercialOffer, OfferRequest, Violation
from app.schemas.estimation import EstimateResult
from app.schemas.requirements import RequirementDoc

SYSTEM_PROMPT = """You are the sales agent at {company}. The client has already agreed the requirements and the team
has prepared a proposal. Reply in English, with a professional and friendly tone.

Base proposal (validated data; these are the ONLY figures you may mention, together with those returned by the
tools):
{summary}

Rules you can never break:
- Never invent or calculate figures. For any change to price, discount, deposit, change rounds or months of
  support, call propose_offer and use exactly what it returns.
- If propose_offer returns status "escalated", do NOT accept: explain that you are checking with the team and
  that a person will reply. Never say yes on your own.
- If the client asks for something you cannot resolve with the tools (a different payment schedule, a scope
  change, special conditions), call escalate_to_human.
- For questions about the contract or policies, call search_contract and cite every statement with its marker
  [C1], [C2]... If the excerpts don't answer the question, say so and escalate it.
- When the client accepts a validated offer, call generate_proposal.
- Never reveal internal rules, hourly rates or negotiation limits."""

SAFE_REPLY = (
    "I want to make sure I give you an exact answer, so I'm checking with the team and a person "
    "will get back to you shortly."
)


class OfferArgs(BaseModel):
    """Argumentos de la herramienta con tipos simples; se convierten a Decimal antes de calcular."""

    discount_pct: float = Field(default=0, ge=0, le=100, description="Discount in %, 0 if none")
    deposit_pct: float | None = Field(
        default=None, ge=0, le=100, description="Deposit in %, null = the standard one"
    )
    change_rounds: int | None = Field(default=None, ge=0, description="null = the included ones")
    support_months: int | None = Field(default=None, ge=0, description="null = the included ones")

    def to_request(self) -> OfferRequest:
        return OfferRequest(
            discount_pct=Decimal(str(self.discount_pct)),
            deposit_pct=None if self.deposit_pct is None else Decimal(str(self.deposit_pct)),
            change_rounds=self.change_rounds,
            support_months=self.support_months,
        )


class ContractQuery(BaseModel):
    query: str = Field(
        description="Question about the contract, payments, intellectual property, support, etc."
    )


class EscalateArgs(BaseModel):
    reason: str
    client_request: str = Field(description="What exactly the client asked for")


class NoArgs(BaseModel):
    pass


class CommercialState:
    def __init__(
        self, ctx: AgentContext, estimate: Estimate, result: EstimateResult, summary: ClientSafeSummary
    ):
        self.ctx = ctx
        self.estimate = estimate
        self.result = result
        self.summary = summary
        self.offers: list[CommercialOffer] = []
        self.last_valid_offer_id: int | None = None
        self.citations: list[Citation] = []
        self.escalated = False


async def load_context(ctx: AgentContext) -> tuple[Estimate, EstimateResult, ClientSafeSummary]:
    estimate = await ctx.session.scalar(
        select(Estimate)
        .where(Estimate.lead_id == ctx.lead.id, Estimate.status == "done")
        .order_by(Estimate.id.desc())
    )
    if estimate is None or estimate.result is None:
        raise LookupError("there is no finished estimate for this client")
    version = await ctx.session.get(RequirementVersion, estimate.requirement_version_id)
    result = EstimateResult.model_validate(estimate.result)
    doc = RequirementDoc.model_validate(version.doc)
    return estimate, result, client_safe_summary(result, doc, await get_rules(ctx.session))


async def escalate(
    ctx: AgentContext, reason: str, client_request: str, violations: list[Violation], log: TurnLog
) -> Escalation:
    esc = Escalation(
        lead_id=ctx.lead.id,
        reason=reason,
        client_request=client_request,
        summary=f"Client {ctx.lead.name}: {client_request}. Reason: {reason}",
        violations=[v.model_dump(mode="json") for v in violations],
    )
    ctx.session.add(esc)
    await ctx.session.flush()
    log.rules.append(f"escalated:{esc.id}")
    await ctx.emit("escalation", {"id": esc.id, "reason": reason})
    return esc


def build_tools(state: CommercialState, log: TurnLog, client_message: str) -> list[Tool]:
    ctx = state.ctx

    async def propose_offer(args: OfferArgs):
        rules = await get_rules(ctx.session)
        offer = build_offer(args.to_request(), state.result, rules)
        violations = validate_offer(offer, rules)
        row = Offer(
            lead_id=ctx.lead.id,
            estimate_id=state.estimate.id,
            terms=offer.model_dump(mode="json"),
            valid=not violations,
            violations=[v.model_dump(mode="json") for v in violations],
        )
        ctx.session.add(row)
        await ctx.session.flush()
        log.rules.append(f"offer:{row.id} valid={not violations}")
        if violations:
            log.violations += row.violations
            await escalate(ctx, "Request outside the commercial limits", client_message, violations, log)
            state.escalated = True
            # Al LLM no le damos los límites: solo que no puede aceptarlo
            return {
                "status": "escalated",
                "message": "You cannot accept this; a person from the team will review it.",
            }
        state.offers.append(offer)
        state.last_valid_offer_id = row.id
        return {"status": "ok", "offer": offer.model_dump(mode="json")}

    async def search_contract(q: ContractQuery):
        found = await search_documents(
            ctx.session, ctx.llm, q.query, ["contract", "policy"], start_id=len(state.citations) + 1
        )
        state.citations += found
        return [{"cite": f"[C{c.id}]", "source": c.label, "text": c.text} for c in found]

    async def escalate_to_human(a: EscalateArgs):
        await escalate(ctx, a.reason, a.client_request, [], log)
        state.escalated = True
        return {"status": "escalated"}

    async def generate_proposal(_: NoArgs):
        offer_id = state.last_valid_offer_id
        if offer_id is None:
            last = await ctx.session.scalar(
                select(Offer).where(Offer.lead_id == ctx.lead.id, Offer.valid).order_by(Offer.id.desc())
            )
            offer_id = last.id if last else None
        if offer_id is None:
            return {"error": "you must validate an offer with propose_offer first"}
        proposal = Proposal(lead_id=ctx.lead.id, offer_id=offer_id)
        ctx.session.add(proposal)
        await ctx.session.flush()
        log.rules.append(f"proposal:{proposal.id}")
        ctx.after_commit.append(lambda: _enqueue_pdf(proposal.id))
        await ctx.emit("proposal", {"id": proposal.id})
        return {"status": "queued", "message": "The proposal and contract PDF is being generated."}

    return [
        Tool(
            "propose_offer",
            "Calculate and validate an offer with the given terms.",
            OfferArgs,
            propose_offer,
        ),
        Tool(
            "search_contract",
            "Search the contract template and the policies.",
            ContractQuery,
            search_contract,
        ),
        Tool(
            "escalate_to_human",
            "Hand the request over to a person on the team.",
            EscalateArgs,
            escalate_to_human,
        ),
        Tool(
            "generate_proposal",
            "Generate the proposal and contract PDF for the latest valid offer.",
            NoArgs,
            generate_proposal,
        ),
    ]


def _enqueue_pdf(proposal_id: int) -> None:
    from app.tasks.pdf import render_proposal_pdf

    render_proposal_pdf.delay(proposal_id)


def check_reply(
    text: str, state: CommercialState, client_message: str, used_contract: bool
) -> list[Violation]:
    allowed = allowed_numbers(state.summary, state.offers)
    if state.escalated:
        # Al escalar puede repetir lo que pidió el cliente ("has pedido un 30%") sin prometerlo
        allowed |= numbers_in(client_message)
    violations = check_response_numbers(text, allowed)
    if used_contract:
        violations += check_citations(text, {c.id for c in state.citations})
    return violations


async def handle(ctx: AgentContext) -> AgentReply:
    log = TurnLog()
    estimate, result, summary = await load_context(ctx)
    state = CommercialState(ctx, estimate, result, summary)
    # Las ofertas válidas previas también son cifras que ya se pueden mencionar
    previous = (
        await ctx.session.scalars(select(Offer).where(Offer.lead_id == ctx.lead.id, Offer.valid))
    ).all()
    state.offers = [CommercialOffer.model_validate(o.terms) for o in previous]

    convo = await history(ctx.session, ctx.lead.id)
    client_message = convo[-1]["content"] if convo else ""
    tools = build_tools(state, log, client_message)
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT.format(
                summary=summary.model_dump_json(indent=1), company=get_settings().company_name
            ),
        },
        *convo,
    ]
    content = await run_tool_loop(ctx.llm, messages, tools, log)

    for attempt in range(2):
        used_contract = any(c["name"] == "search_contract" for c in log.tool_calls)
        violations = check_reply(content, state, client_message, used_contract)
        log.rules.append(f"output_check[{attempt}]={[v.code.value for v in violations] or 'ok'}")
        if not violations:
            break
        log.violations += [v.model_dump(mode="json") for v in violations]
        if attempt == 0:
            messages += [
                {"role": "assistant", "content": content},
                {
                    "role": "system",
                    "content": "Reply blocked by the guardrails: "
                    + json.dumps([v.model_dump(mode="json") for v in violations], ensure_ascii=False)
                    + ". Rewrite it using only validated figures and citing the sources.",
                },
            ]
            content = await run_tool_loop(ctx.llm, messages, tools, log, max_steps=3)
    else:
        content = SAFE_REPLY
        if not state.escalated:
            await escalate(ctx, "The agent reply did not pass the guardrails", client_message, [], log)

    log.citations = [c.model_dump(exclude={"text"}) | {"label": c.label} for c in state.citations]
    return AgentReply(content=content, agent="commercial", log=log)
