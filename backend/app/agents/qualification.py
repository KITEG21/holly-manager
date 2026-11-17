"""Agente de cualificación: ¿es un cliente real?

El LLM extrae evidencias (con cita) y redacta la siguiente pregunta. La nota y la decisión las toma el código.
"""

from app.agents.base import AgentContext, AgentReply, TurnLog, history
from app.core.config import get_settings
from app.domain.guardrails import check_response_numbers
from app.domain.scoring import score_qualification
from app.models import Stage
from app.repo import get_criteria, get_rules, get_thresholds
from app.schemas.qualification import Evidence, QualificationEvidence, QualificationStatus

EXTRACT_PROMPT = """From this conversation with a prospective client of a software agency, extract:
- budget_eur: approximate budget in euros (convert '20k' to 20000).
- timeline_weeks: desired timeline in weeks (convert months to weeks: 1 month = 4.3 weeks).
- is_decision_maker: true if the person talking makes the hiring decision.
- company_name: their company's name.
- email: contact email.
- need_clarity: from 1 (very vague idea) to 5 (clear goals, users and scope).
For each field, put in `quote` the client's literal sentence that supports it. If they haven't said it, value = null."""

ASK_PROMPT = """You are the sales assistant of {company}, a software development agency.
Reply in English, in 1-3 sentences, with a friendly and professional tone.
Briefly acknowledge what the client just said and ask ONLY this question: "{question}"
Do not mention scores, prices, timelines or discounts."""

FIRST_REQUIREMENTS_QUESTION = (
    "Thanks! With that I can move on to understanding your project properly. "
    "Tell me: what problem do you want to solve, and who is going to use the application?"
)
NURTURE_REPLY = (
    "Thanks for sharing your idea. Right now it isn't quite a fit for how we work, "
    "but we'd love to stay in touch: we'll send you some useful resources, and once it's "
    "more defined we can pick the conversation back up."
)
DISCARD_REPLY = (
    "Thanks for your interest. From what you've told us, we aren't the right team "
    "for this project right now. Best of luck with it!"
)


async def first_question(ctx: AgentContext) -> str:
    criteria = [c for c in await get_criteria(ctx.session) if c.enabled]
    q = criteria[0].question if criteria else "What would you like to build?"
    return f"Hi {ctx.lead.name}! I'm the {get_settings().company_name} assistant. To point you in the right direction: {q}"


async def handle(ctx: AgentContext) -> AgentReply:
    log = TurnLog()
    criteria = await get_criteria(ctx.session)
    thresholds = await get_thresholds(ctx.session)
    rules = await get_rules(ctx.session)

    convo = await history(ctx.session, ctx.lead.id)
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in convo)
    evidence = await ctx.llm.structured(
        [{"role": "system", "content": EXTRACT_PROMPT}, {"role": "user", "content": transcript}],
        QualificationEvidence,
    )
    if ctx.lead.email and not evidence.email.value:
        evidence.email = Evidence(value=ctx.lead.email, quote="(sign-up form)")

    result = score_qualification(evidence, criteria, thresholds, rules.min_price)
    ctx.lead.qualification_score = result.score
    ctx.lead.qualification_status = result.status
    ctx.lead.qualification_detail = {
        "evidence": evidence.model_dump(mode="json"),
        "result": result.model_dump(mode="json"),
        "explanation": result.explanation,
    }
    log.rules.append(f"qualification.score={result.score} status={result.status}")
    await ctx.emit("qualification", ctx.lead.qualification_detail)

    if result.status == QualificationStatus.pending:
        question = next(c.question for c in criteria if c.key == result.missing[0])
        resp = await ctx.llm.chat(
            [
                {
                    "role": "system",
                    "content": ASK_PROMPT.format(question=question, company=get_settings().company_name),
                },
                *convo[-6:],
            ]
        )
        content = resp.content or question
        # Guardrail: este agente nunca debe hablar de cifras comerciales
        if violations := check_response_numbers(content, set()):
            log.violations += [v.model_dump(mode="json") for v in violations]
            content = question
        return AgentReply(content=content, agent="qualification", log=log)

    if result.status == QualificationStatus.qualified:
        ctx.lead.stage = Stage.requirements
        content = FIRST_REQUIREMENTS_QUESTION
    elif result.status == QualificationStatus.nurture:
        ctx.lead.stage = Stage.nurture
        content = NURTURE_REPLY
    else:
        ctx.lead.stage = Stage.discarded
        content = DISCARD_REPLY
    await ctx.emit("stage", ctx.lead.stage)
    return AgentReply(content=content, agent="qualification", log=log)
