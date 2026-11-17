from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

V = TypeVar("V")


class CriterionKey(StrEnum):
    budget = "budget"
    timeline = "timeline"
    decision_maker = "decision_maker"
    company = "company"
    corporate_email = "corporate_email"
    need_clarity = "need_clarity"


class QualificationCriterionConfig(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: CriterionKey
    question: str
    weight: float = Field(ge=0)
    enabled: bool = True


class Evidence(BaseModel, Generic[V]):
    """Un dato extraído por el LLM junto a la frase literal del cliente que lo justifica."""

    value: V | None = None
    quote: str | None = Field(default=None, description="Literal client quote that supports the value")


class QualificationEvidence(BaseModel):
    budget_eur: Evidence[float] = Evidence()
    timeline_weeks: Evidence[float] = Evidence()
    is_decision_maker: Evidence[bool] = Evidence()
    company_name: Evidence[str] = Evidence()
    email: Evidence[str] = Evidence()
    need_clarity: Evidence[int] = Field(
        default=Evidence(), description="1 = muy vaga, 5 = objetivos y alcance claros"
    )


class QualificationStatus(StrEnum):
    pending = "pending"
    qualified = "qualified"
    nurture = "nurture"
    discarded = "discarded"


class ScoreLine(BaseModel):
    key: CriterionKey
    weight: float
    factor: float  # 0..1
    points: float
    reason: str
    quote: str | None = None


class QualificationResult(BaseModel):
    score: float
    status: QualificationStatus
    lines: list[ScoreLine]
    missing: list[CriterionKey]

    @property
    def explanation(self) -> str:
        parts = [f"{line.reason} ({line.points:+.0f})" for line in self.lines]
        return f"Score {self.score:.0f} because: " + "; ".join(parts)
