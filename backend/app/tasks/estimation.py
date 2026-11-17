"""Motor de estimación y sprints (interno). El LLM descompone; RAG aporta histórico; el código calcula."""

import asyncio
import json

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import task_session
from app.core.llm import LiteLLMClient, LLMClient
from app.core.telemetry import set_json_attr, tracer
from app.domain.estimation import estimate_task, totals
from app.domain.pricing import build_quote
from app.domain.scheduling import SchedulingError, plan_sprints, topological_order
from app.domain.summary import client_safe_summary, format_money
from app.models import Escalation, Estimate, Lead, Message, ProjectTask, RequirementVersion, Stage
from app.rag.retrieve import similar_tasks
from app.repo import get_rules, get_task_types, get_team
from app.schemas.config import CommercialRules, TaskTypeConfig, TeamConfig
from app.schemas.estimation import Decomposition, EstimateResult
from app.schemas.requirements import RequirementDoc
from app.worker import celery_app

DECOMPOSE_PROMPT = """You are a tech lead. Break each user story down into concrete technical tasks.
- Each task has exactly one type from this list: {types}.
- Include QA tasks for stories with acceptance criteria, and DevOps tasks if there is deployment or infrastructure.
- Use ids T1, T2... and in depends_on only ids of tasks from this same list. No circular dependencies.
- Write task titles in English.
- Do NOT estimate hours or effort: only break the work down.
Non-functional requirements to take into account: {nfrs}"""


def validate_decomposition(
    dec: Decomposition, doc: RequirementDoc, types: dict[str, TaskTypeConfig]
) -> list[str]:
    problems = []
    story_ids = {s.id for s in doc.stories}
    task_ids = [t.id for t in dec.tasks]
    if len(set(task_ids)) != len(task_ids):
        problems.append("there are duplicate task ids")
    for t in dec.tasks:
        if t.task_type not in types:
            problems.append(f"{t.id}: type '{t.task_type}' is not allowed")
        if t.story_id not in story_ids:
            problems.append(f"{t.id}: story '{t.story_id}' does not exist")
        for d in t.depends_on:
            if d not in task_ids:
                problems.append(f"{t.id}: depends on '{d}', which does not exist")
    uncovered = story_ids - {t.story_id for t in dec.tasks}
    if uncovered:
        problems.append(f"stories without tasks: {', '.join(sorted(uncovered))}")
    return problems


async def decompose(llm: LLMClient, doc: RequirementDoc, types: dict[str, TaskTypeConfig]) -> Decomposition:
    stories = [
        s.model_dump(include={"id", "as_a", "i_want", "so_that", "acceptance_criteria"}) for s in doc.stories
    ]
    messages = [
        {
            "role": "system",
            "content": DECOMPOSE_PROMPT.format(
                types=", ".join(types), nfrs="; ".join(n.text for n in doc.nfrs) or "ninguno"
            ),
        },
        {"role": "user", "content": json.dumps(stories, ensure_ascii=False)},
    ]
    for _ in range(3):
        dec = await llm.structured(messages, Decomposition)
        problems = validate_decomposition(dec, doc, types)
        if not problems:
            try:
                topological_order([estimate_task(t, types[t.task_type], [], 0) for t in dec.tasks])
                return dec
            except SchedulingError as e:
                problems = [str(e)]
        messages += [
            {"role": "assistant", "content": dec.model_dump_json()},
            {"role": "user", "content": f"Fix these problems: {problems}"},
        ]
    raise ValueError(f"the breakdown is not valid: {problems}")


async def compute_estimate(
    session: AsyncSession,
    llm: LLMClient,
    doc: RequirementDoc,
    types: dict[str, TaskTypeConfig],
    team: TeamConfig,
    rules: CommercialRules,
) -> EstimateResult:
    with tracer.start_as_current_span("estimation.compute") as span:
        dec = await decompose(llm, doc, types)
        history = await similar_tasks(
            session, llm, [f"{t.title}" for t in dec.tasks], [t.task_type for t in dec.tasks]
        )
        estimates = [
            estimate_task(
                t, types[t.task_type], h, rules.risk_margin_pct, get_settings().history_min_similarity
            )
            for t, h in zip(dec.tasks, history, strict=True)
        ]
        sprints, warnings = plan_sprints(estimates, team.effective_capacity)
        tot = totals(estimates, rules.risk_margin_pct)
        result = EstimateResult(
            tasks=estimates,
            sprints=sprints,
            totals=tot,
            quote=build_quote(tot.committed_hours, rules),
            weeks=len(sprints) * team.sprint_weeks,
            scope_exceeds_max=tot.committed_hours > rules.max_scope_hours,
            warnings=warnings,
        )
        span.set_attribute("estimation.tasks", len(estimates))
        span.set_attribute("estimation.committed_hours", tot.committed_hours)
        set_json_attr(span, "estimation.totals", tot.model_dump())
        return result


def proposal_message(result: EstimateResult, doc: RequirementDoc, rules: CommercialRules) -> str:
    s = client_safe_summary(result, doc, rules)
    payments = "; ".join(
        f"{p.name} {p.pct.normalize():f}% ({format_money(p.amount, s.currency)})" for p in s.payments
    )
    return (
        f"Your proposal is ready! The project ({', '.join(s.epics)}) is priced at "
        f"{format_money(s.list_price, s.currency)} and would be delivered in {s.weeks} weeks ({s.sprint_count} sprints). "
        f"Payments: {payments}. It includes {s.included_change_rounds} change rounds and {s.support_months} months of support. "
        "Would you like to go over any of the terms, or shall I prepare the proposal and contract as a PDF?"
    )


async def materialize_tasks(session: AsyncSession, estimate: Estimate, result: EstimateResult) -> None:
    """Convierte la estimación en el backlog que ejecuta el equipo de desarrollo."""
    await session.execute(delete(ProjectTask).where(ProjectTask.estimate_id == estimate.id))
    sprint_of = {tid: s.number for s in result.sprints for tid in s.task_ids}
    session.add_all(
        ProjectTask(
            lead_id=estimate.lead_id,
            estimate_id=estimate.id,
            key=t.task.id,
            story_id=t.task.story_id,
            title=t.task.title,
            task_type=t.task.task_type,
            depends_on=t.task.depends_on,
            sprint=sprint_of[t.task.id],
            planned_hours=t.planned_hours,
        )
        for t in result.tasks
    )


async def run_estimation(session: AsyncSession, llm: LLMClient, estimate_id: int) -> None:
    estimate = await session.get(Estimate, estimate_id)
    version = await session.get(RequirementVersion, estimate.requirement_version_id)
    lead = await session.get(Lead, estimate.lead_id)
    doc = RequirementDoc.model_validate(version.doc)
    rules = await get_rules(session)
    estimate.status = "running"
    await session.commit()

    try:
        result = await compute_estimate(
            session, llm, doc, await get_task_types(session), await get_team(session), rules
        )
    except Exception as e:  # noqa: BLE001  cualquier fallo acaba en manos de una persona
        # compute_estimate solo lee, así que no hay nada que deshacer
        estimate.status, estimate.error = "failed", str(e)
        session.add(
            Escalation(
                lead_id=lead.id,
                reason="Automatic estimation failed",
                client_request="estimate",
                summary=str(e)[:2000],
            )
        )
        session.add(
            Message(
                lead_id=lead.id,
                role="assistant",
                agent="system",
                content="The team is going to review the estimate personally and will message you shortly.",
            )
        )
        await session.commit()
        raise

    estimate.status, estimate.result = "done", result.model_dump(mode="json")
    await materialize_tasks(session, estimate, result)
    lead.stage = Stage.commercial
    if result.scope_exceeds_max:
        session.add(
            Escalation(
                lead_id=lead.id,
                reason="The scope exceeds the maximum that can be committed without review",
                client_request="proposal",
                summary=f"{result.totals.committed_hours:g} h committed > {rules.max_scope_hours:g} h",
            )
        )
        content = "This is a large project and we want to review it carefully: a person from the team will send you the proposal."
    else:
        content = proposal_message(result, doc, rules)
    session.add(Message(lead_id=lead.id, role="assistant", agent="commercial", content=content, meta={}))
    await session.commit()


@celery_app.task(name="estimate_project", bind=True, max_retries=0)
def estimate_project(self, estimate_id: int) -> None:
    async def _run():
        async with task_session() as session:
            await run_estimation(session, LiteLLMClient(), estimate_id)

    asyncio.run(_run())
