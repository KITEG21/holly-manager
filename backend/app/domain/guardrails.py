"""Guardrails comerciales.

Tres capas, todas deterministas:
1. `build_offer` calcula el precio a partir de los términos pedidos: el LLM nunca escribe un importe.
2. `validate_offer` comprueba la oferta contra las reglas configuradas.
3. `check_response_numbers` / `check_citations` revisan el texto final antes de enviarlo al cliente.
"""

import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation

from app.domain.pricing import apply_discount, money, payment_schedule
from app.schemas.commercial import (
    ClientSafeSummary,
    CommercialOffer,
    OfferRequest,
    Violation,
    ViolationCode,
)
from app.schemas.config import CommercialRules
from app.schemas.estimation import EstimateResult


def build_offer(req: OfferRequest, estimate: EstimateResult, rules: CommercialRules) -> CommercialOffer:
    base = estimate.quote.list_price
    price = apply_discount(base, req.discount_pct)
    deposit = rules.deposit_pct if req.deposit_pct is None else req.deposit_pct
    return CommercialOffer(
        currency=rules.currency,
        list_price=base,
        discount_pct=req.discount_pct,
        price=price,
        deposit_pct=deposit,
        payments=payment_schedule(price, rules, deposit),
        change_rounds=rules.included_change_rounds if req.change_rounds is None else req.change_rounds,
        support_months=rules.support_months if req.support_months is None else req.support_months,
        scope_hours=estimate.totals.committed_hours,
        weeks=estimate.weeks,
    )


def validate_offer(offer: CommercialOffer, rules: CommercialRules) -> list[Violation]:
    v: list[Violation] = []
    if offer.discount_pct > rules.max_discount_pct:
        v.append(
            Violation(
                code=ViolationCode.discount_exceeds_max,
                message="The requested discount exceeds the maximum allowed.",
                requested=f"{offer.discount_pct}%",
                limit=f"{rules.max_discount_pct}%",
            )
        )
    if offer.price < rules.min_price:
        v.append(
            Violation(
                code=ViolationCode.price_below_min,
                message="The price falls below the minimum.",
                requested=str(offer.price),
                limit=str(rules.min_price),
            )
        )
    if offer.price != apply_discount(offer.list_price, offer.discount_pct):
        v.append(
            Violation(
                code=ViolationCode.price_mismatch, message="The price does not match the rate and discount."
            )
        )
    if offer.deposit_pct < rules.deposit_pct:
        v.append(
            Violation(
                code=ViolationCode.deposit_below_min,
                message="The deposit is lower than required.",
                requested=f"{offer.deposit_pct}%",
                limit=f"{rules.deposit_pct}%",
            )
        )
    if (
        sum((p.amount for p in offer.payments), Decimal(0)) != offer.price
        or sum((p.pct for p in offer.payments), Decimal(0)) != 100
    ):
        v.append(
            Violation(code=ViolationCode.payments_not_100, message="The payments do not add up to 100%.")
        )
    if offer.change_rounds > rules.included_change_rounds:
        v.append(
            Violation(
                code=ViolationCode.change_rounds_exceed,
                message="More change rounds were requested than are included.",
                requested=str(offer.change_rounds),
                limit=str(rules.included_change_rounds),
            )
        )
    if offer.support_months > rules.support_months:
        v.append(
            Violation(
                code=ViolationCode.support_exceeds,
                message="More months of support were requested than are included.",
                requested=str(offer.support_months),
                limit=str(rules.support_months),
            )
        )
    if offer.scope_hours > rules.max_scope_hours:
        v.append(
            Violation(
                code=ViolationCode.scope_exceeds_max,
                message="The scope exceeds the maximum that can be committed without human review.",
                requested=f"{offer.scope_hours:g} h",
                limit=f"{rules.max_scope_hours:g} h",
            )
        )
    return v


# --- Comprobaciones sobre el texto de salida ---------------------------------------------------

# Solo vigilamos números con unidad comercial: importes, porcentajes y plazos/condiciones.
_NUMBER_WITH_UNIT = re.compile(
    r"(?P<pre>[€$]\s?)?(?<![\d.,])(?P<num>\d{1,3}(?:[.,\s]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)(?!\d)"
    r"\s?(?P<unit>%|€|eur\b|euros?\b|usd\b|\$|months?\b|weeks?\b|rounds?\b|hours?\b|hrs?\b|"
    r"mes(?:es)?\b|semanas?\b|rondas?\b|horas?\b|sprints?\b|h\b)?",
    re.IGNORECASE,
)


def _candidates(token: str) -> set[Decimal]:
    """Interpretaciones posibles de un número escrito en formato español o inglés."""
    token = token.replace(" ", "")
    options = {
        token.replace(".", "").replace(",", "."),  # 12.500,50 -> 12500.50
        token.replace(",", ""),  # 12,500.50 -> 12500.50
    }
    out = set()
    for o in options:
        try:
            out.add(Decimal(o).normalize())
        except InvalidOperation:
            continue
    return out


def allowed_numbers(summary: ClientSafeSummary, offers: Iterable[CommercialOffer] = ()) -> set[Decimal]:
    nums: list[Decimal | int] = [
        summary.list_price,
        summary.weeks,
        summary.sprint_count,
        summary.included_change_rounds,
        summary.support_months,
    ]
    for p in summary.payments:
        nums += [p.amount, p.pct]
    for o in offers:
        nums += [
            o.price,
            o.list_price,
            o.discount_pct,
            o.deposit_pct,
            o.change_rounds,
            o.support_months,
            o.weeks,
        ]
        nums += [money(o.list_price - o.price)]
        for p in o.payments:
            nums += [p.amount, p.pct]
    return {Decimal(str(n)).normalize() for n in nums}


def numbers_in(text: str) -> set[Decimal]:
    out: set[Decimal] = set()
    for m in _NUMBER_WITH_UNIT.finditer(text):
        out |= _candidates(m.group("num"))
    return out


def check_response_numbers(text: str, allowed: set[Decimal]) -> list[Violation]:
    bad: list[str] = []
    for m in _NUMBER_WITH_UNIT.finditer(text):
        if not (m.group("pre") or m.group("unit")):
            continue
        token = m.group("num")
        if _candidates(token) & allowed:
            continue
        bad.append(m.group(0).strip())
    if not bad:
        return []
    return [
        Violation(
            code=ViolationCode.unvalidated_number,
            message="The reply contains commercial figures that do not come from a validated offer.",
            requested=", ".join(bad),
        )
    ]


_CITATION = re.compile(r"\[C(\d+)\]")


def cited_ids(text: str) -> set[int]:
    return {int(x) for x in _CITATION.findall(text)}


def check_citations(text: str, valid_ids: set[int]) -> list[Violation]:
    cited = cited_ids(text)
    if cited and cited <= valid_ids:
        return []
    return [
        Violation(
            code=ViolationCode.missing_citation,
            message="Answers about the contract or policies must cite the excerpts used, e.g. [C1].",
            requested=", ".join(f"C{c}" for c in sorted(cited - valid_ids)) or None,
        )
    ]
