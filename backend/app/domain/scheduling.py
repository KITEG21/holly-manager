"""Reparto de tareas en sprints según capacidad efectiva y dependencias."""

import heapq

from app.schemas.estimation import SprintPlan, TaskEstimate


class SchedulingError(ValueError):
    pass


def topological_order(estimates: list[TaskEstimate]) -> list[TaskEstimate]:
    """Kahn con desempate por orden original, para que el resultado sea estable."""
    by_id = {e.task.id: e for e in estimates}
    if len(by_id) != len(estimates):
        raise SchedulingError("duplicate task ids")
    position = {e.task.id: i for i, e in enumerate(estimates)}
    indegree = {tid: 0 for tid in by_id}
    dependents: dict[str, list[str]] = {tid: [] for tid in by_id}
    for e in estimates:
        for dep in e.task.depends_on:
            if dep not in by_id:
                raise SchedulingError(f"{e.task.id} depends on {dep}, which does not exist")
            indegree[e.task.id] += 1
            dependents[dep].append(e.task.id)

    ready = [(position[t], t) for t, d in indegree.items() if d == 0]
    heapq.heapify(ready)
    ordered: list[TaskEstimate] = []
    while ready:
        _, tid = heapq.heappop(ready)
        ordered.append(by_id[tid])
        for nxt in dependents[tid]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                heapq.heappush(ready, (position[nxt], nxt))
    if len(ordered) != len(estimates):
        cyclic = sorted(t for t, d in indegree.items() if d > 0)
        raise SchedulingError(f"circular dependencies between: {', '.join(cyclic)}")
    return ordered


def plan_sprints(estimates: list[TaskEstimate], capacity_hours: float) -> tuple[list[SprintPlan], list[str]]:
    """First-fit: cada tarea va al primer sprint con hueco que no sea anterior a sus dependencias.

    Una dependencia puede estar en el mismo sprint (se trabaja en orden dentro del sprint).
    """
    if capacity_hours <= 0:
        raise SchedulingError("effective capacity must be positive")
    warnings: list[str] = []
    sprint_tasks: list[list[str]] = []
    sprint_load: list[float] = []
    sprint_of: dict[str, int] = {}

    for e in topological_order(estimates):
        hours = e.planned_hours
        earliest = max((sprint_of[d] for d in e.task.depends_on), default=0)
        if hours > capacity_hours:
            warnings.append(
                f"{e.task.id} ({hours:g} h) exceeds the sprint capacity ({capacity_hours:g} h): consider splitting it"
            )
        idx = next(
            (i for i in range(earliest, len(sprint_load)) if sprint_load[i] + hours <= capacity_hours),
            None,
        )
        if idx is None:
            # Una tarea sobredimensionada ocupa un sprint vacío en lugar de bloquear el plan
            idx = next((i for i in range(earliest, len(sprint_load)) if sprint_load[i] == 0), None)
        if idx is None:
            sprint_tasks.append([])
            sprint_load.append(0.0)
            idx = len(sprint_load) - 1
        sprint_tasks[idx].append(e.task.id)
        sprint_load[idx] += hours
        sprint_of[e.task.id] = idx

    sprints = [
        SprintPlan(number=i + 1, task_ids=ids, planned_hours=round(load, 2), capacity_hours=capacity_hours)
        for i, (ids, load) in enumerate(zip(sprint_tasks, sprint_load, strict=True))
    ]
    return sprints, warnings
