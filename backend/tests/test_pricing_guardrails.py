from decimal import Decimal

import pytest

from app.domain.guardrails import (
    allowed_numbers,
    build_offer,
    check_citations,
    check_response_numbers,
    validate_offer,
)
from app.domain.pricing import build_quote, payment_schedule
from app.schemas.commercial import ClientSafeSummary, OfferRequest, ViolationCode
from app.schemas.estimation import EstimateResult, EstimateTotals
from tests.factories import D, rules


def estimate(hours: float = 300, r=None) -> EstimateResult:
    r = r or rules()
    return EstimateResult(
        tasks=[],
        sprints=[],
        totals=EstimateTotals(
            expected_hours=hours, std_dev_hours=0, p80_hours=hours, risk_margin_pct=0, committed_hours=hours
        ),
        quote=build_quote(hours, r),
        weeks=8,
        scope_exceeds_max=hours > r.max_scope_hours,
    )


def codes(vs):
    return {v.code for v in vs}


def test_quote_uses_rate_and_min_price():
    q = build_quote(300, rules())
    assert q.list_price == D("16500.00")  # 300 h * 55
    assert not q.min_price_applied
    small = build_quote(10, rules())
    assert small.list_price == D("6000.00")
    assert small.min_price_applied


def test_payments_add_up_exactly_even_with_odd_cents():
    lines = payment_schedule(D("10000.01"), rules())
    assert sum(line.amount for line in lines) == D("10000.01")
    assert sum(line.pct for line in lines) == 100
    assert lines[0].name == "Deposit" and lines[0].pct == 30


def test_higher_deposit_rebalances_milestones():
    lines = payment_schedule(D("1000"), rules(), deposit_pct=D("50"))
    assert [line.pct for line in lines] == [D("50"), D("28.57"), D("21.43")]
    assert sum(line.amount for line in lines) == D("1000")


def test_rules_reject_payments_not_summing_100():
    with pytest.raises(ValueError, match="100%"):
        rules(deposit_pct=D("50"))


def test_offer_within_limits_is_valid():
    r = rules()
    offer = build_offer(OfferRequest(discount_pct=D("10")), estimate(r=r), r)
    assert offer.price == D("14850.00")
    assert validate_offer(offer, r) == []


@pytest.mark.parametrize(
    ("req", "code"),
    [
        (OfferRequest(discount_pct=D("10.1")), ViolationCode.discount_exceeds_max),
        (OfferRequest(deposit_pct=D("20")), ViolationCode.deposit_below_min),
        (OfferRequest(change_rounds=3), ViolationCode.change_rounds_exceed),
        (OfferRequest(support_months=6), ViolationCode.support_exceeds),
    ],
)
def test_out_of_limits_requests_are_flagged(req, code):
    r = rules()
    assert code in codes(validate_offer(build_offer(req, estimate(r=r), r), r))


def test_discount_cannot_push_price_below_minimum():
    r = rules(max_discount_pct=D("50"))
    offer = build_offer(OfferRequest(discount_pct=D("50")), estimate(hours=150, r=r), r)  # 8250 -> 4125
    assert ViolationCode.price_below_min in codes(validate_offer(offer, r))


def test_scope_above_max_requires_human():
    r = rules(max_scope_hours=100)
    offer = build_offer(OfferRequest(), estimate(hours=300, r=r), r)
    assert ViolationCode.scope_exceeds_max in codes(validate_offer(offer, r))


def test_tampered_price_is_detected():
    r = rules()
    offer = build_offer(OfferRequest(), estimate(r=r), r).model_copy(update={"price": D("1")})
    assert ViolationCode.price_mismatch in codes(validate_offer(offer, r))


def summary(r=None) -> ClientSafeSummary:
    r = r or rules()
    q = build_quote(300, r)
    return ClientSafeSummary(
        currency="EUR",
        list_price=q.list_price,
        weeks=8,
        sprint_count=4,
        payments=q.payments,
        included_change_rounds=2,
        support_months=3,
        epics=[],
        out_of_scope=[],
    )


def test_response_with_validated_numbers_passes():
    allowed = allowed_numbers(summary())
    text = "El precio es 16.500,00 € en 8 semanas, con un anticipo del 30% y 2 rondas de cambios."
    assert check_response_numbers(text, allowed) == []


def test_response_with_invented_discount_is_blocked():
    allowed = allowed_numbers(summary())
    vs = check_response_numbers("Te puedo hacer un 25% de descuento, quedaría en 12.375 €", allowed)
    assert vs and vs[0].code == ViolationCode.unvalidated_number
    assert "25%" in vs[0].requested


def test_validated_offer_numbers_become_allowed():
    r = rules()
    offer = build_offer(OfferRequest(discount_pct=D("5")), estimate(r=r), r)
    allowed = allowed_numbers(summary(r), [offer])
    assert check_response_numbers("Con un 5% de descuento queda en 15,675.00 EUR", allowed) == []


def test_numbers_without_commercial_unit_are_ignored():
    assert check_response_numbers("La historia US-3 tiene 4 criterios", set()) == []


def test_citations_required_and_must_exist():
    assert check_citations("Según la cláusula [C1], el pago es a 30 días.", {1, 2}) == []
    assert check_citations("El pago es a 30 días.", {1})[0].code == ViolationCode.missing_citation
    assert check_citations("Ver [C9].", {1})[0].requested == "C9"


def test_decimal_type_is_preserved():
    assert isinstance(build_quote(1, rules()).price, Decimal)


def test_plain_decimal_price_is_read_as_one_number():
    assert check_response_numbers("quedaría en 2701.33 €", {Decimal("2701.33")}) == []
    assert check_response_numbers("son 12 000 €", {Decimal("12000")}) == []
