"""Gestión de tareas y tiempo para el equipo. Cada imputación re-estima el proyecto con código determinista."""

import logging
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TeamOnly, current_user
from app.core.db import get_session
from app.domain.forecast import Forecast, TaskProgress, forecast_project
from app.models import (
    Estimate,
    HistoricalTask,
    Lead,
    ProjectTask,
    RequirementVersion,
    Role,
    TaskStatus,
    TimeEntry,
    User,
)
from app.repo import get_team
from app.schemas.estimation import EstimateResult
from app.schemas.requirements import RequirementDoc

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dev", tags=["dev"], dependencies=[TeamOnly])
Session = Depends(get_session)
Me = Depends(current_user)

# Hasta cuántos días atrás se puede imputar (para corregir la hoja de horas sin reescribir la historia)
MAX_BACKDATE_DAYS = 60


class TaskOut(BaseModel):
    id: int
    key: str
    lead_id: int
    project: str
    story_id: str
    story: str  # trazabilidad: la historia acordada con el cliente de la que sale la tarea
    title: str
    task_type: str
    depends_on: list[str]
    sprint: int
    planned_hours: float
    actual_hours: float
    status: TaskStatus
    blocked_by: list[str]  # dependencias que aún no están hechas
    assignee_id: int | None
    assignee: str | None
    done_at: datetime | None


class SprintOut(BaseModel):
    number: int
    planned_hours: float
    actual_hours: float
    tasks: list[TaskOut]


class ProjectSummary(BaseModel):
    lead_id: int
    name: str
    forecast: Forecast


class ProjectDetail(ProjectSummary):
    sprint_weeks: int
    sprints: list[SprintOut]


# --- Carga y construcción ---------------------------------------------------------------------


async def _latest_estimate_ids(session: AsyncSession) -> dict[int, int]:
    """Backlog vigente de cada proyecto: el de su última estimación."""
    rows = await session.execute(
        select(ProjectTask.lead_id, func.max(ProjectTask.estimate_id)).group_by(ProjectTask.lead_id)
    )
    return dict(rows.all())


async def _load(session: AsyncSession, lead_id: int) -> tuple[Lead, Estimate, list[ProjectTask]]:
    lead = await session.get(Lead, lead_id)
    estimate_id = (await _latest_estimate_ids(session)).get(lead_id)
    if lead is None or estimate_id is None:
        raise HTTPException(404, "project has no backlog")
    tasks = (
        await session.scalars(
            select(ProjectTask).where(ProjectTask.estimate_id == estimate_id).order_by(ProjectTask.id)
        )
    ).all()
    return lead, await session.get(Estimate, estimate_id), list(tasks)


async def _forecast(session: AsyncSession, estimate: Estimate, tasks: list[ProjectTask]) -> Forecast:
    team = await get_team(session)
    committed = EstimateResult.model_validate(estimate.result).totals.committed_hours
    return forecast_project(
        [
            TaskProgress(
                key=t.key, planned_hours=t.planned_hours, actual_hours=t.actual_hours, status=t.status
            )
            for t in tasks
        ],
        committed,
        team.effective_capacity,
        team.deviation_alert_pct,
    )


def _blocked_by(task: ProjectTask, by_key: dict[str, ProjectTask]) -> list[str]:
    return [d for d in task.depends_on if d in by_key and by_key[d].status != TaskStatus.done]


async def _user_names(session: AsyncSession) -> dict[int, str]:
    return dict((await session.execute(select(User.id, User.name))).all())


async def _stories(session: AsyncSession, estimate: Estimate) -> dict[str, str]:
    version = await session.get(RequirementVersion, estimate.requirement_version_id)
    doc = RequirementDoc.model_validate(version.doc)
    return {s.id: f"Como {s.as_a}, quiero {s.i_want}" for s in doc.stories}


async def _task_outs(session: AsyncSession, lead_id: int) -> tuple[Lead, Estimate, list[TaskOut]]:
    lead, estimate, tasks = await _load(session, lead_id)
    stories = await _stories(session, estimate)
    names = await _user_names(session)
    by_key = {t.key: t for t in tasks}
    return (
        lead,
        estimate,
        [
            TaskOut(
                id=t.id,
                key=t.key,
                lead_id=lead.id,
                project=lead.name,
                story_id=t.story_id,
                story=stories.get(t.story_id, ""),
                title=t.title,
                task_type=t.task_type,
                depends_on=t.depends_on,
                sprint=t.sprint,
                planned_hours=t.planned_hours,
                actual_hours=t.actual_hours,
                status=t.status,
                blocked_by=_blocked_by(t, by_key),
                assignee_id=t.assignee_id,
                assignee=names.get(t.assignee_id) if t.assignee_id else None,
                done_at=t.done_at,
            )
            for t in tasks
        ],
    )


# --- Proyectos ----------------------------------------------------------------------------------


@router.get("/projects")
async def list_projects(session: AsyncSession = Session) -> list[ProjectSummary]:
    out = []
    for lead_id in sorted(await _latest_estimate_ids(session)):
        lead, estimate, tasks = await _load(session, lead_id)
        out.append(
            ProjectSummary(
                lead_id=lead.id, name=lead.name, forecast=await _forecast(session, estimate, tasks)
            )
        )
    return out


@router.get("/projects/{lead_id}")
async def project_detail(lead_id: int, session: AsyncSession = Session) -> ProjectDetail:
    lead, estimate, tasks = await _task_outs(session, lead_id)
    rows = (await session.scalars(select(ProjectTask).where(ProjectTask.estimate_id == estimate.id))).all()
    sprints: dict[int, list[TaskOut]] = defaultdict(list)
    for t in tasks:
        sprints[t.sprint].append(t)
    team = await get_team(session)
    return ProjectDetail(
        lead_id=lead.id,
        name=lead.name,
        forecast=await _forecast(session, estimate, list(rows)),
        sprint_weeks=team.sprint_weeks,
        sprints=[
            SprintOut(
                number=n,
                planned_hours=round(sum(t.planned_hours for t in ts), 1),
                actual_hours=round(sum(t.actual_hours for t in ts), 1),
                tasks=ts,
            )
            for n, ts in sorted(sprints.items())
        ],
    )


# --- Tareas -------------------------------------------------------------------------------------


@router.get("/tasks")
async def list_tasks(
    mine: bool = False,
    status: TaskStatus | None = None,
    user: User = Me,
    session: AsyncSession = Session,
) -> list[TaskOut]:
    """Tareas de todos los proyectos vigentes, con filtros para la vista «Mis tareas»."""
    out: list[TaskOut] = []
    for lead_id in sorted(await _latest_estimate_ids(session)):
        _, _, tasks = await _task_outs(session, lead_id)
        out += [
            t
            for t in tasks
            if (not mine or t.assignee_id == user.id) and (status is None or t.status == status)
        ]
    return out


class Member(BaseModel):
    id: int
    name: str
    role: Role


@router.get("/team")
async def team_members(session: AsyncSession = Session) -> list[Member]:
    rows = (
        await session.scalars(
            select(User).where(User.role.in_([Role.developer, Role.admin])).order_by(User.name)
        )
    ).all()
    return [Member(id=u.id, name=u.name, role=u.role) for u in rows]


async def _sync_history(session: AsyncSession, task: ProjectTask, lead: Lead) -> bool:
    """Las tareas cerradas alimentan el histórico que usa el RAG para estimar los siguientes proyectos.

    Devuelve True si hay que (re)calcular embeddings.
    """
    row = await session.scalar(select(HistoricalTask).where(HistoricalTask.source_task_id == task.id))
    if task.status != TaskStatus.done:
        if row:
            await session.delete(row)
        return False
    if row:
        row.actual_hours = task.actual_hours
        return False
    session.add(
        HistoricalTask(
            project=lead.name,
            title=task.title,
            task_type=task.task_type,
            estimated_hours=task.planned_hours,
            actual_hours=task.actual_hours,
            source_task_id=task.id,
        )
    )
    return True


def _enqueue_embeddings() -> None:
    from app.tasks.ingest import embed_historical_task

    try:
        embed_historical_task.delay()
    except Exception:  # noqa: BLE001  el embedding se puede recalcular más tarde; no bloquea al dev
        log.exception("could not enqueue embed_historical")


class TaskChange(BaseModel):
    task: TaskOut
    forecast: Forecast


async def _change(session: AsyncSession, task_id: int) -> TaskChange:
    task = await session.get(ProjectTask, task_id)
    lead, estimate, tasks = await _task_outs(session, task.lead_id)
    rows = (await session.scalars(select(ProjectTask).where(ProjectTask.estimate_id == estimate.id))).all()
    return TaskChange(
        task=next(t for t in tasks if t.id == task_id),
        forecast=await _forecast(session, estimate, list(rows)),
    )


async def _get_task(session: AsyncSession, task_id: int) -> ProjectTask:
    task = await session.get(ProjectTask, task_id)
    if task is None:
        raise HTTPException(404, "task not found")
    return task


class TaskUpdate(BaseModel):
    status: TaskStatus


@router.patch("/tasks/{task_id}")
async def update_task(task_id: int, data: TaskUpdate, session: AsyncSession = Session) -> TaskChange:
    task = await _get_task(session, task_id)
    lead, _, tasks = await _load(session, task.lead_id)
    if data.status != TaskStatus.todo and (blocked := _blocked_by(task, {t.key: t for t in tasks})):
        raise HTTPException(409, f"these tasks must be finished first: {', '.join(blocked)}")
    if data.status == TaskStatus.done and task.actual_hours <= 0:
        raise HTTPException(422, "log the actual hours before closing the task")
    if data.status == TaskStatus.done and task.status != TaskStatus.done:
        task.done_at = datetime.now(UTC)
    elif data.status != TaskStatus.done:
        task.done_at = None
    task.status = data.status
    needs_embedding = await _sync_history(session, task, lead)
    await session.commit()
    if needs_embedding:
        _enqueue_embeddings()
    return await _change(session, task_id)


class AssignIn(BaseModel):
    user_id: int | None


@router.post("/tasks/{task_id}/assign")
async def assign_task(task_id: int, data: AssignIn, session: AsyncSession = Session) -> TaskChange:
    task = await _get_task(session, task_id)
    if data.user_id is not None:
        member = await session.get(User, data.user_id)
        if member is None or member.role == Role.client:
            raise HTTPException(422, "tasks can only be assigned to team members")
    task.assignee_id = data.user_id
    await session.commit()
    return await _change(session, task_id)


# --- Tiempo -------------------------------------------------------------------------------------


class TimeIn(BaseModel):
    hours: float = Field(gt=0, le=24)
    note: str | None = Field(default=None, max_length=500)
    work_date: date | None = None

    @field_validator("work_date")
    @classmethod
    def _not_future(cls, v: date | None) -> date | None:
        if v is None:
            return v
        today = date.today()
        if v > today:
            raise ValueError("you cannot log hours in the future")
        if v < today - timedelta(days=MAX_BACKDATE_DAYS):
            raise ValueError(f"you can only log hours up to {MAX_BACKDATE_DAYS} days back")
        return v


class TimeOut(BaseModel):
    id: int
    task_id: int
    hours: float
    note: str | None
    user_id: int
    user: str
    work_date: date
    created_at: datetime


async def _day_total(session: AsyncSession, user_id: int, day: date) -> float:
    total = await session.scalar(
        select(func.coalesce(func.sum(TimeEntry.hours), 0)).where(
            TimeEntry.user_id == user_id, TimeEntry.work_date == day
        )
    )
    return float(total or 0)


@router.post("/tasks/{task_id}/time")
async def log_time(
    task_id: int, data: TimeIn, user: User = Me, session: AsyncSession = Session
) -> TaskChange:
    task = await _get_task(session, task_id)
    lead, _, tasks = await _load(session, task.lead_id)
    day = data.work_date or date.today()
    if await _day_total(session, user.id, day) + data.hours > 24:
        raise HTTPException(422, f"this would exceed 24 h logged on {day:%b %d}")
    if task.status == TaskStatus.todo:
        if blocked := _blocked_by(task, {t.key: t for t in tasks}):
            raise HTTPException(409, f"these tasks must be finished first: {', '.join(blocked)}")
        task.status = TaskStatus.in_progress
    if task.assignee_id is None:
        task.assignee_id = user.id  # quien imputa primero se queda la tarea
    session.add(TimeEntry(task_id=task.id, user_id=user.id, hours=data.hours, note=data.note, work_date=day))
    task.actual_hours = round(task.actual_hours + data.hours, 2)
    await _sync_history(session, task, lead)
    await session.commit()
    return await _change(session, task_id)


@router.delete("/time/{entry_id}")
async def delete_time(entry_id: int, user: User = Me, session: AsyncSession = Session) -> TaskChange:
    entry = await session.get(TimeEntry, entry_id)
    if entry is None:
        raise HTTPException(404, "time entry not found")
    if entry.user_id != user.id and user.role != Role.admin:
        raise HTTPException(403, "you can only delete your own time entries")
    task = await _get_task(session, entry.task_id)
    lead = await session.get(Lead, task.lead_id)
    task.actual_hours = max(round(task.actual_hours - entry.hours, 2), 0)
    await session.delete(entry)
    await _sync_history(session, task, lead)
    await session.commit()
    return await _change(session, task.id)


async def _time_rows(session: AsyncSession, *where) -> list[TimeOut]:
    rows = (
        await session.execute(
            select(TimeEntry, User.name)
            .join(User, User.id == TimeEntry.user_id)
            .where(*where)
            .order_by(TimeEntry.work_date.desc(), TimeEntry.id.desc())
        )
    ).all()
    return [
        TimeOut(
            id=e.id,
            task_id=e.task_id,
            hours=e.hours,
            note=e.note,
            user_id=e.user_id,
            user=name,
            work_date=e.work_date,
            created_at=e.created_at,
        )
        for e, name in rows
    ]


@router.get("/tasks/{task_id}/time")
async def list_time(task_id: int, session: AsyncSession = Session) -> list[TimeOut]:
    await _get_task(session, task_id)
    return await _time_rows(session, TimeEntry.task_id == task_id)


class TimesheetRow(BaseModel):
    task_id: int
    key: str
    title: str
    project: str
    status: TaskStatus
    hours: list[float]  # una posición por día de la semana (lunes a domingo)
    total: float


class Timesheet(BaseModel):
    week_start: date
    days: list[date]
    rows: list[TimesheetRow]
    day_totals: list[float]
    total: float
    entries: list[TimeOut]


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


@router.get("/timesheet")
async def timesheet(
    week_start: date | None = Query(default=None, description="Any day of the week; its Monday is used"),
    user: User = Me,
    session: AsyncSession = Session,
) -> Timesheet:
    start = monday(week_start or date.today())
    days = [start + timedelta(days=i) for i in range(7)]
    entries = await _time_rows(
        session, TimeEntry.user_id == user.id, TimeEntry.work_date >= days[0], TimeEntry.work_date <= days[-1]
    )
    task_ids = {e.task_id for e in entries}
    tasks = (
        {
            t.id: t
            for t in (await session.scalars(select(ProjectTask).where(ProjectTask.id.in_(task_ids)))).all()
        }
        if task_ids
        else {}
    )
    leads = dict((await session.execute(select(Lead.id, Lead.name))).all())
    grid: dict[int, list[float]] = defaultdict(lambda: [0.0] * 7)
    for e in entries:
        grid[e.task_id][(e.work_date - start).days] += e.hours
    rows = [
        TimesheetRow(
            task_id=tid,
            key=tasks[tid].key,
            title=tasks[tid].title,
            project=leads.get(tasks[tid].lead_id, ""),
            status=tasks[tid].status,
            hours=[round(h, 2) for h in hours],
            total=round(sum(hours), 2),
        )
        for tid, hours in sorted(grid.items(), key=lambda kv: (tasks[kv[0]].lead_id, kv[0]))
    ]
    day_totals = [round(sum(r.hours[i] for r in rows), 2) for i in range(7)]
    return Timesheet(
        week_start=start,
        days=days,
        rows=rows,
        day_totals=day_totals,
        total=round(sum(day_totals), 2),
        entries=entries,
    )


# --- Panel e informes ---------------------------------------------------------------------------


class Activity(BaseModel):
    user: str
    hours: float
    work_date: date
    note: str | None
    task_id: int
    key: str
    title: str
    project: str
    lead_id: int


class Dashboard(BaseModel):
    today_hours: float
    week_hours: float
    week_target_hours: float
    my_open_tasks: int
    my_in_progress: int
    team_done_this_week: int
    projects: list[ProjectSummary]
    my_tasks: list[TaskOut]
    activity: list[Activity]


async def _activity(session: AsyncSession, limit: int) -> list[Activity]:
    rows = (
        await session.execute(
            select(TimeEntry, User.name, ProjectTask, Lead.name)
            .join(User, User.id == TimeEntry.user_id)
            .join(ProjectTask, ProjectTask.id == TimeEntry.task_id)
            .join(Lead, Lead.id == ProjectTask.lead_id)
            .order_by(TimeEntry.created_at.desc(), TimeEntry.id.desc())
            .limit(limit)
        )
    ).all()
    return [
        Activity(
            user=uname,
            hours=e.hours,
            work_date=e.work_date,
            note=e.note,
            task_id=t.id,
            key=t.key,
            title=t.title,
            project=pname,
            lead_id=t.lead_id,
        )
        for e, uname, t, pname in rows
    ]


async def _hours(session: AsyncSession, user_id: int, start: date, end: date) -> float:
    total = await session.scalar(
        select(func.coalesce(func.sum(TimeEntry.hours), 0)).where(
            TimeEntry.user_id == user_id, TimeEntry.work_date >= start, TimeEntry.work_date <= end
        )
    )
    return round(float(total or 0), 2)


@router.get("/dashboard")
async def dashboard(user: User = Me, session: AsyncSession = Session) -> Dashboard:
    today = date.today()
    week = monday(today)
    team = await get_team(session)
    projects = await list_projects(session)
    tasks = await list_tasks(mine=True, status=None, user=user, session=session)
    week_start_dt = datetime.combine(week, datetime.min.time(), tzinfo=UTC)
    done_this_week = await session.scalar(
        select(func.count(ProjectTask.id)).where(ProjectTask.done_at >= week_start_dt)
    )
    open_tasks = [t for t in tasks if t.status != TaskStatus.done]
    return Dashboard(
        today_hours=await _hours(session, user.id, today, today),
        week_hours=await _hours(session, user.id, week, today),
        # Objetivo semanal por persona según la capacidad configurada del equipo
        week_target_hours=round(team.capacity_hours_per_sprint / team.members / team.sprint_weeks, 1),
        my_open_tasks=len(open_tasks),
        my_in_progress=sum(t.status == TaskStatus.in_progress for t in tasks),
        team_done_this_week=done_this_week or 0,
        projects=projects,
        my_tasks=sorted(open_tasks, key=lambda t: (t.status != TaskStatus.in_progress, t.sprint, t.id))[:6],
        activity=await _activity(session, 10),
    )


class TypeAccuracy(BaseModel):
    task_type: str
    tasks: int
    planned_hours: float
    actual_hours: float
    ratio: float  # real / planificado; >1 = se subestima ese tipo de tarea


class WeeklyHours(BaseModel):
    week_start: date
    user: str
    hours: float


class Reports(BaseModel):
    projects: list[ProjectSummary]
    accuracy_by_type: list[TypeAccuracy]
    weekly_hours: list[WeeklyHours]
    weeks: list[date]


@router.get("/reports")
async def reports(weeks: int = Query(default=6, ge=1, le=26), session: AsyncSession = Session) -> Reports:
    done = (await session.scalars(select(ProjectTask).where(ProjectTask.status == TaskStatus.done))).all()
    by_type: dict[str, list[ProjectTask]] = defaultdict(list)
    for t in done:
        by_type[t.task_type].append(t)
    accuracy = [
        TypeAccuracy(
            task_type=k,
            tasks=len(ts),
            planned_hours=round(sum(t.planned_hours for t in ts), 1),
            actual_hours=round(sum(t.actual_hours for t in ts), 1),
            ratio=round(sum(t.actual_hours for t in ts) / sum(t.planned_hours for t in ts), 2)
            if sum(t.planned_hours for t in ts)
            else 0,
        )
        for k, ts in sorted(by_type.items())
    ]

    first = monday(date.today()) - timedelta(weeks=weeks - 1)
    week_list = [first + timedelta(weeks=i) for i in range(weeks)]
    rows = (
        await session.execute(
            select(TimeEntry.work_date, TimeEntry.hours, User.name)
            .join(User, User.id == TimeEntry.user_id)
            .where(TimeEntry.work_date >= first)
        )
    ).all()
    totals: dict[tuple[date, str], float] = defaultdict(float)
    for work_date, hours, name in rows:
        totals[(monday(work_date), name)] += hours
    return Reports(
        projects=await list_projects(session),
        accuracy_by_type=accuracy,
        weekly_hours=[
            WeeklyHours(week_start=w, user=u, hours=round(h, 2)) for (w, u), h in sorted(totals.items())
        ],
        weeks=week_list,
    )
