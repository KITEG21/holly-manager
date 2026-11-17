from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

from app.schemas.estimation import PaymentLine


class OfferRequest(BaseModel):
    """Términos que el agente comercial quiere ofrecer. El precio no se pide: lo calcula el código."""

    discount_pct: Decimal = Field(default=Decimal(0), ge=0, le=100)
    deposit_pct: Decimal | None = Field(default=None, ge=0, le=100)
    change_rounds: int | None = Field(default=None, ge=0)
    support_months: int | None = Field(default=None, ge=0)


class CommercialOffer(BaseModel):
    currency: str
    list_price: Decimal
    discount_pct: Decimal
    price: Decimal
    deposit_pct: Decimal
    payments: list[PaymentLine]
    change_rounds: int
    support_months: int
    scope_hours: float
    weeks: int


class ViolationCode(StrEnum):
    discount_exceeds_max = "DISCOUNT_EXCEEDS_MAX"
    price_below_min = "PRICE_BELOW_MIN"
    price_mismatch = "PRICE_MISMATCH"
    deposit_below_min = "DEPOSIT_BELOW_MIN"
    payments_not_100 = "PAYMENTS_NOT_100"
    change_rounds_exceed = "CHANGE_ROUNDS_EXCEED"
    support_exceeds = "SUPPORT_EXCEEDS"
    scope_exceeds_max = "SCOPE_EXCEEDS_MAX"
    unvalidated_number = "UNVALIDATED_NUMBER"
    missing_citation = "MISSING_CITATION"


class Violation(BaseModel):
    code: ViolationCode
    message: str
    requested: str | None = None
    limit: str | None = None


class ClientSafeSummary(BaseModel):
    """Lo único de la estimación que ve el agente comercial (y por tanto el cliente)."""

    currency: str
    list_price: Decimal
    weeks: int
    sprint_count: int
    payments: list[PaymentLine]
    included_change_rounds: int
    support_months: int
    epics: list[str]
    out_of_scope: list[str]
