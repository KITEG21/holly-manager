"""Puntuación de cualificación. El LLM solo aporta evidencias; aquí se decide la nota y su explicación."""

from decimal import Decimal

from app.schemas.config import QualificationThresholds
from app.schemas.qualification import (
    CriterionKey,
    QualificationCriterionConfig,
    QualificationEvidence,
    QualificationResult,
    QualificationStatus,
    ScoreLine,
)

FREE_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "hotmail.com",
    "hotmail.es",
    "outlook.com",
    "outlook.es",
    "live.com",
    "yahoo.com",
    "yahoo.es",
    "icloud.com",
    "me.com",
    "proton.me",
    "protonmail.com",
    "gmx.com",
    "aol.com",
}


def _factor(
    key: CriterionKey, ev: QualificationEvidence, th: QualificationThresholds, min_price: Decimal
) -> tuple[float, str, str | None] | None:
    """Devuelve (factor 0..1, motivo, cita) o None si todavía no hay evidencia para ese criterio."""
    match key:
        case CriterionKey.budget:
            b = ev.budget_eur
            if b.value is None:
                return None
            ratio = b.value / float(min_price) if min_price else 1.0
            if ratio >= 1:
                return 1.0, f"budget {b.value:,.0f} covers the minimum {min_price:,.0f}", b.quote
            if ratio >= 0.5:
                return 0.5, f"budget {b.value:,.0f} below the minimum {min_price:,.0f}", b.quote
            return 0.0, f"budget {b.value:,.0f} far below the minimum", b.quote
        case CriterionKey.timeline:
            t = ev.timeline_weeks
            if t.value is None:
                return None
            if t.value >= th.min_timeline_weeks:
                return 1.0, f"timeline of {t.value:g} weeks is realistic", t.quote
            return (
                0.3,
                f"timeline of {t.value:g} weeks is below the minimum ({th.min_timeline_weeks})",
                t.quote,
            )
        case CriterionKey.decision_maker:
            d = ev.is_decision_maker
            if d.value is None:
                return None
            if d.value:
                return 1.0, "talking to the decision maker", d.quote
            return 0.3, "not the decision maker", d.quote
        case CriterionKey.company:
            c = ev.company_name
            if not c.value:
                return None
            return 1.0, f"company identified ({c.value})", c.quote
        case CriterionKey.corporate_email:
            e = ev.email
            if not e.value or "@" not in e.value:
                return None
            domain = e.value.rsplit("@", 1)[1].lower().strip()
            if domain in FREE_EMAIL_DOMAINS:
                return 0.2, f"personal email ({domain})", e.quote
            return 1.0, f"company email ({domain})", e.quote
        case CriterionKey.need_clarity:
            n = ev.need_clarity
            if n.value is None:
                return None
            level = min(max(n.value, 1), 5)
            return (level - 1) / 4, f"need clarity {level}/5", n.quote
    raise ValueError(f"unknown criterion: {key}")


def score_qualification(
    evidence: QualificationEvidence,
    criteria: list[QualificationCriterionConfig],
    thresholds: QualificationThresholds,
    min_price: Decimal,
) -> QualificationResult:
    active = [c for c in criteria if c.enabled and c.weight > 0]
    total_weight = sum(c.weight for c in active)
    lines: list[ScoreLine] = []
    missing: list[CriterionKey] = []
    for c in active:
        result = _factor(c.key, evidence, thresholds, min_price)
        if result is None:
            missing.append(c.key)
            continue
        factor, reason, quote = result
        points = 100 * c.weight * factor / total_weight if total_weight else 0
        lines.append(
            ScoreLine(
                key=c.key, weight=c.weight, factor=factor, points=round(points, 1), reason=reason, quote=quote
            )
        )
    # Los criterios sin evidencia puntúan 0: no se premia lo que no se sabe.
    score = round(sum(line.points for line in lines), 1)

    if missing:
        status = QualificationStatus.pending
    elif score >= thresholds.qualified:
        status = QualificationStatus.qualified
    elif score >= thresholds.nurture:
        status = QualificationStatus.nurture
    else:
        status = QualificationStatus.discarded
    return QualificationResult(score=score, status=status, lines=lines, missing=missing)
