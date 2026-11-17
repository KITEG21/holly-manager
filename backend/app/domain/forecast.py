"""Re-estimación con el avance real. Determinista: el ritmo observado en las tareas cerradas se proyecta
sobre las pendientes."""

import math

from pydantic import BaseModel


class TaskProgress(BaseModel):
    key: str
    planned_hours: float
    actual_hours: float
    status: str  # todo | in_progress | done


class Forecast(BaseModel):
    committed_hours: float
    logged_hours: float
    remaining_hours: float
    forecast_hours: float
    performance_ratio: float  # horas reales / planificadas en las tareas cerradas; 1 = según lo previsto
    deviation_pct: float
    done_tasks: int
    total_tasks: int
    remaining_sprints: int
    alert: bool
    alert_message: str | None = None


def forecast_project(
    tasks: list[TaskProgress], committed_hours: float, sprint_capacity_hours: float, alert_pct: float
) -> Forecast:
    done = [t for t in tasks if t.status == "done"]
    planned_done = sum(t.planned_hours for t in done)
    # Sin tareas cerradas no hay ritmo observado: se mantiene el plan
    ratio = sum(t.actual_hours for t in done) / planned_done if planned_done > 0 else 1.0

    logged = sum(t.actual_hours for t in tasks)
    # Lo pendiente de cada tarea abierta: su plan ajustado al ritmo, menos lo ya imputado
    remaining = sum(max(t.planned_hours * ratio - t.actual_hours, 0) for t in tasks if t.status != "done")
    total = logged + remaining
    deviation = (total - committed_hours) / committed_hours * 100 if committed_hours else 0.0

    alert = deviation > alert_pct
    message = None
    if alert:
        message = (
            f"The forecast ({total:.0f} h) exceeds the committed hours ({committed_hours:.0f} h) "
            f"by {deviation:.0f}%; the alert threshold is {alert_pct:g}%."
        )
    return Forecast(
        committed_hours=round(committed_hours, 1),
        logged_hours=round(logged, 1),
        remaining_hours=round(remaining, 1),
        forecast_hours=round(total, 1),
        performance_ratio=round(ratio, 2),
        deviation_pct=round(deviation, 1),
        done_tasks=len(done),
        total_tasks=len(tasks),
        remaining_sprints=math.ceil(remaining / sprint_capacity_hours) if sprint_capacity_hours > 0 else 0,
        alert=alert,
        alert_message=message,
    )
