"""Precio y calendario de pagos. Decimal en todo el camino: el dinero no se redondea con floats."""

from decimal import ROUND_HALF_UP, Decimal

from app.schemas.config import CommercialRules
from app.schemas.estimation import PaymentLine, Quote

CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def list_price(hours: float, rules: CommercialRules) -> tuple[Decimal, bool]:
    raw = money(Decimal(str(hours)) * rules.hourly_rate)
    if raw < rules.min_price:
        return money(rules.min_price), True
    return raw, False


def apply_discount(price: Decimal, discount_pct: Decimal) -> Decimal:
    return money(price * (1 - discount_pct / 100))


def payment_schedule(
    price: Decimal, rules: CommercialRules, deposit_pct: Decimal | None = None
) -> list[PaymentLine]:
    """Anticipo + hitos. Si cambia el anticipo, la diferencia se reparte proporcionalmente entre los hitos.

    El último pago absorbe los céntimos del redondeo para que la suma sea exacta.
    """
    deposit = rules.deposit_pct if deposit_pct is None else deposit_pct
    remaining_pct = 100 - deposit
    base_ms_total = sum((m.pct for m in rules.milestones), Decimal(0))
    pcts: list[tuple[str, Decimal]] = [("Deposit", deposit)]
    for m in rules.milestones:
        pct = m.pct * remaining_pct / base_ms_total if base_ms_total else Decimal(0)
        pcts.append((m.name, pct.quantize(Decimal("0.01"))))
    # Ajuste de redondeo de porcentajes
    drift = 100 - sum(p for _, p in pcts)
    name, last = pcts[-1]
    pcts[-1] = (name, last + drift)

    lines = [PaymentLine(name=n, pct=p, amount=money(price * p / 100)) for n, p in pcts if p > 0]
    drift_amount = price - sum(line.amount for line in lines)
    lines[-1].amount += drift_amount
    return lines


def build_quote(hours: float, rules: CommercialRules, discount_pct: Decimal = Decimal(0)) -> Quote:
    base, min_applied = list_price(hours, rules)
    price = apply_discount(base, discount_pct)
    return Quote(
        currency=rules.currency,
        hourly_rate=rules.hourly_rate,
        hours=hours,
        list_price=base,
        min_price_applied=min_applied,
        discount_pct=discount_pct,
        price=price,
        payments=payment_schedule(price, rules),
    )
