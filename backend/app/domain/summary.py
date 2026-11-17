from app.schemas.commercial import ClientSafeSummary
from app.schemas.config import CommercialRules
from app.schemas.estimation import EstimateResult
from app.schemas.requirements import RequirementDoc


def client_safe_summary(
    est: EstimateResult, doc: RequirementDoc, rules: CommercialRules
) -> ClientSafeSummary:
    """Filtra la estimación interna: ni horas, ni tarifa, ni margen de riesgo, ni límites de negociación."""
    return ClientSafeSummary(
        currency=est.quote.currency,
        list_price=est.quote.list_price,
        weeks=est.weeks,
        sprint_count=len(est.sprints),
        payments=est.quote.payments,
        included_change_rounds=rules.included_change_rounds,
        support_months=rules.support_months,
        epics=[e.title for e in doc.epics],
        out_of_scope=doc.out_of_scope,
    )


def format_money(amount, currency: str) -> str:
    # Formato inglés: €16,500.00
    symbols = {"EUR": "€", "USD": "$", "GBP": "£"}
    text = f"{amount:,.2f}"
    return f"{symbols[currency]}{text}" if currency in symbols else f"{text} {currency}"
