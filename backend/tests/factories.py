from decimal import Decimal

from app.domain.estimation import estimate_task
from app.schemas.config import CommercialRules, Complexity, TaskTypeConfig
from app.schemas.estimation import TaskDraft, TaskEstimate

TASK_TYPES = {
    "backend": TaskTypeConfig(name="backend", min_hours=8, max_hours=24, complexity=Complexity.medium),
    "frontend": TaskTypeConfig(name="frontend", min_hours=6, max_hours=20, complexity=Complexity.medium),
    "qa": TaskTypeConfig(name="qa", min_hours=2, max_hours=6, complexity=Complexity.low),
}


def rules(**overrides) -> CommercialRules:
    return CommercialRules(**overrides)


def task(tid: str, deps: list[str] | None = None, task_type: str = "backend") -> TaskDraft:
    return TaskDraft(
        id=tid, story_id="US-1", title=f"Tarea {tid}", task_type=task_type, depends_on=deps or []
    )


def est(tid: str, hours: float, deps: list[str] | None = None) -> TaskEstimate:
    """Estimación con horas planificadas fijas, para testear el reparto en sprints."""
    e = estimate_task(task(tid, deps), TASK_TYPES["backend"], [], 0)
    return e.model_copy(update={"planned_hours": hours})


D = Decimal
