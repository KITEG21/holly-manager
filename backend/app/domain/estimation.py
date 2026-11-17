"""Estimación de tres puntos (PERT). Las horas salen de los rangos configurados y del histórico real."""

import math
import statistics

from app.schemas.config import Complexity, TaskTypeConfig
from app.schemas.estimation import EstimateTotals, HistoricalMatch, TaskDraft, TaskEstimate

# Cuánto se abre el caso pesimista según la complejidad del tipo de tarea
PESSIMISM_BY_COMPLEXITY = {Complexity.low: 1.0, Complexity.medium: 1.15, Complexity.high: 1.3}
# Similitud coseno mínima para usar una tarea histórica; depende del modelo de embeddings
MIN_SIMILARITY = 0.6
Z_P80 = 0.8416


def estimate_task(
    task: TaskDraft,
    task_type: TaskTypeConfig,
    history: list[HistoricalMatch],
    risk_margin_pct: float,
    min_similarity: float = MIN_SIMILARITY,
) -> TaskEstimate:
    optimistic = task_type.min_hours
    pessimistic = task_type.max_hours * PESSIMISM_BY_COMPLEXITY[task_type.complexity]
    likely = (task_type.min_hours + task_type.max_hours) / 2
    refs = [h for h in history if h.similarity >= min_similarity and h.task_type == task_type.name]

    if refs:
        median_actual = statistics.median(h.actual_hours for h in refs)
        # El histórico real manda, pero puede ampliar el rango si el pasado se salió de él
        likely = median_actual
        optimistic = min(optimistic, min(h.actual_hours for h in refs))
        pessimistic = max(pessimistic, max(h.actual_hours for h in refs))
        basis = f"median of {len(refs)} similar tasks ({median_actual:g} h) over the {task_type.name} range"
    else:
        basis = f"configured {task_type.name} range ({task_type.min_hours:g}-{task_type.max_hours:g} h)"

    expected = (optimistic + 4 * likely + pessimistic) / 6
    std_dev = (pessimistic - optimistic) / 6
    return TaskEstimate(
        task=task,
        optimistic=round(optimistic, 2),
        likely=round(likely, 2),
        pessimistic=round(pessimistic, 2),
        expected=round(expected, 2),
        std_dev=round(std_dev, 2),
        planned_hours=round(expected * (1 + risk_margin_pct / 100), 2),
        historical_refs=refs,
        basis=basis,
    )


def totals(estimates: list[TaskEstimate], risk_margin_pct: float) -> EstimateTotals:
    expected = sum(e.expected for e in estimates)
    # Tareas independientes: las varianzas se suman
    sigma = math.sqrt(sum(e.std_dev**2 for e in estimates))
    p80 = expected + Z_P80 * sigma
    with_margin = expected * (1 + risk_margin_pct / 100)
    return EstimateTotals(
        expected_hours=round(expected, 1),
        std_dev_hours=round(sigma, 1),
        p80_hours=round(p80, 1),
        risk_margin_pct=risk_margin_pct,
        # Comprometemos lo más prudente de los dos criterios
        committed_hours=round(max(with_margin, p80), 1),
    )
