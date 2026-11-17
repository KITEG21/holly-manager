from decimal import Decimal

from app.domain.scoring import score_qualification
from app.schemas.config import QualificationThresholds
from app.schemas.qualification import (
    CriterionKey,
    Evidence,
    QualificationCriterionConfig,
    QualificationEvidence,
    QualificationStatus,
)

CRITERIA = [
    QualificationCriterionConfig(key=CriterionKey.budget, question="¿Presupuesto?", weight=30),
    QualificationCriterionConfig(key=CriterionKey.timeline, question="¿Plazo?", weight=15),
    QualificationCriterionConfig(key=CriterionKey.decision_maker, question="¿Decides tú?", weight=20),
    QualificationCriterionConfig(key=CriterionKey.company, question="¿Empresa?", weight=10),
    QualificationCriterionConfig(key=CriterionKey.corporate_email, question="¿Email?", weight=10),
    QualificationCriterionConfig(key=CriterionKey.need_clarity, question="¿Qué necesitas?", weight=15),
]
TH = QualificationThresholds()
MIN_PRICE = Decimal("6000")


def evidence(**kw) -> QualificationEvidence:
    base = dict(
        budget_eur=Evidence(value=20000, quote="tenemos unos 20k"),
        timeline_weeks=Evidence(value=12),
        is_decision_maker=Evidence(value=True),
        company_name=Evidence(value="Acme"),
        email=Evidence(value="ana@acme.io"),
        need_clarity=Evidence(value=5),
    )
    base.update(kw)
    return QualificationEvidence(**base)


def test_perfect_lead_scores_100_and_is_qualified():
    r = score_qualification(evidence(), CRITERIA, TH, MIN_PRICE)
    assert r.score == 100
    assert r.status == QualificationStatus.qualified
    assert not r.missing
    assert "company email (acme.io)" in r.explanation


def test_missing_evidence_keeps_status_pending():
    r = score_qualification(evidence(budget_eur=Evidence()), CRITERIA, TH, MIN_PRICE)
    assert r.status == QualificationStatus.pending
    assert r.missing == [CriterionKey.budget]


def test_free_email_and_low_budget_reduce_score():
    r = score_qualification(
        evidence(email=Evidence(value="ana@gmail.com"), budget_eur=Evidence(value=1000)),
        CRITERIA,
        TH,
        MIN_PRICE,
    )
    # Pierde 30 (presupuesto) + 8 (email al 20%)
    assert r.score == 62
    assert r.status == QualificationStatus.nurture


def test_discarded_below_nurture_threshold():
    r = score_qualification(
        evidence(
            budget_eur=Evidence(value=500),
            is_decision_maker=Evidence(value=False),
            email=Evidence(value="x@gmail.com"),
            need_clarity=Evidence(value=1),
        ),
        CRITERIA,
        TH,
        MIN_PRICE,
    )
    assert r.score < TH.nurture
    assert r.status == QualificationStatus.discarded


def test_disabled_criteria_are_ignored():
    criteria = [c.model_copy(update={"enabled": c.key != CriterionKey.budget}) for c in CRITERIA]
    r = score_qualification(evidence(budget_eur=Evidence()), criteria, TH, MIN_PRICE)
    assert r.status == QualificationStatus.qualified
    assert r.score == 100


def test_score_lines_keep_quotes_for_explainability():
    r = score_qualification(evidence(), CRITERIA, TH, MIN_PRICE)
    budget_line = next(line for line in r.lines if line.key == CriterionKey.budget)
    assert budget_line.quote == "tenemos unos 20k"
