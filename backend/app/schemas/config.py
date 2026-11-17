"""Configuración del panel de administración. Todo número que use el sistema sale de aquí."""

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Complexity(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class TaskTypeConfig(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(min_length=1, max_length=40)
    min_hours: float = Field(gt=0)
    max_hours: float = Field(gt=0)
    complexity: Complexity = Complexity.medium

    @model_validator(mode="after")
    def _range(self) -> "TaskTypeConfig":
        if self.min_hours > self.max_hours:
            raise ValueError("min_hours cannot be greater than max_hours")
        return self


class TeamConfig(BaseModel):
    members: int = Field(ge=1, default=3)
    capacity_hours_per_sprint: float = Field(gt=0, default=180)
    # Fracción de la capacidad que realmente se entrega (velocidad histórica)
    velocity_factor: float = Field(gt=0, le=1.5, default=0.8)
    sprint_weeks: int = Field(ge=1, le=6, default=2)
    # Aviso cuando la re-estimación supera las horas comprometidas en más de este %
    deviation_alert_pct: float = Field(ge=0, le=100, default=10)

    @property
    def effective_capacity(self) -> float:
        return self.capacity_hours_per_sprint * self.velocity_factor


class Milestone(BaseModel):
    name: str
    pct: Decimal = Field(gt=0, le=100)


class CommercialRules(BaseModel):
    currency: str = "EUR"
    hourly_rate: Decimal = Field(gt=0, default=Decimal("55"))
    min_price: Decimal = Field(ge=0, default=Decimal("6000"))
    max_discount_pct: Decimal = Field(ge=0, le=50, default=Decimal("10"))
    deposit_pct: Decimal = Field(ge=0, le=100, default=Decimal("30"))
    milestones: list[Milestone] = Field(
        default_factory=lambda: [
            Milestone(name="Mid-project delivery", pct=Decimal("40")),
            Milestone(name="Final delivery", pct=Decimal("30")),
        ]
    )
    included_change_rounds: int = Field(ge=0, default=2)
    support_months: int = Field(ge=0, default=3)
    max_scope_hours: float = Field(gt=0, default=2000)
    risk_margin_pct: float = Field(ge=0, le=100, default=15)

    @model_validator(mode="after")
    def _payments_sum_100(self) -> "CommercialRules":
        total = self.deposit_pct + sum((m.pct for m in self.milestones), Decimal(0))
        if total != 100:
            raise ValueError(f"deposit + milestones must add up to 100% (they add up to {total}%)")
        return self


class QualificationThresholds(BaseModel):
    qualified: float = Field(ge=0, le=100, default=70)
    nurture: float = Field(ge=0, le=100, default=40)
    min_timeline_weeks: int = Field(ge=0, default=4)

    @model_validator(mode="after")
    def _order(self) -> "QualificationThresholds":
        if self.nurture > self.qualified:
            raise ValueError("the nurture threshold must be <= the qualified threshold")
        return self
