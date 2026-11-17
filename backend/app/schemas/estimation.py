from decimal import Decimal

from pydantic import BaseModel, Field


class TaskDraft(BaseModel):
    """Lo único que produce el LLM: tareas tipadas con dependencias. Nunca horas."""

    id: str = Field(description="Identificador corto, p. ej. T1")
    story_id: str
    title: str
    task_type: str
    depends_on: list[str] = []


class Decomposition(BaseModel):
    tasks: list[TaskDraft]


class HistoricalMatch(BaseModel):
    project: str
    title: str
    task_type: str
    actual_hours: float
    similarity: float


class TaskEstimate(BaseModel):
    task: TaskDraft
    optimistic: float
    likely: float
    pessimistic: float
    expected: float
    std_dev: float
    planned_hours: float  # esperado + margen de riesgo; es lo que se agenda
    historical_refs: list[HistoricalMatch] = []
    basis: str


class SprintPlan(BaseModel):
    number: int
    task_ids: list[str]
    planned_hours: float
    capacity_hours: float


class EstimateTotals(BaseModel):
    expected_hours: float
    std_dev_hours: float
    p80_hours: float
    risk_margin_pct: float
    committed_hours: float


class PaymentLine(BaseModel):
    name: str
    pct: Decimal
    amount: Decimal


class Quote(BaseModel):
    currency: str
    hourly_rate: Decimal
    hours: float
    list_price: Decimal
    min_price_applied: bool
    discount_pct: Decimal = Decimal(0)
    price: Decimal
    payments: list[PaymentLine]


class EstimateResult(BaseModel):
    tasks: list[TaskEstimate]
    sprints: list[SprintPlan]
    totals: EstimateTotals
    quote: Quote
    weeks: int
    scope_exceeds_max: bool
    warnings: list[str] = []
