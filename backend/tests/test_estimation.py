import pytest

from app.domain.estimation import estimate_task, totals
from app.domain.scheduling import SchedulingError, plan_sprints, topological_order
from app.schemas.estimation import HistoricalMatch
from tests.factories import TASK_TYPES, est, task


def test_pert_from_configured_range():
    e = estimate_task(task("T1"), TASK_TYPES["backend"], [], risk_margin_pct=10)
    # O=8, M=16, P=24*1.15=27.6
    assert e.optimistic == 8
    assert e.likely == 16
    assert e.pessimistic == pytest.approx(27.6)
    assert e.expected == pytest.approx((8 + 4 * 16 + 27.6) / 6, abs=0.01)
    assert e.planned_hours == pytest.approx(e.expected * 1.1, abs=0.01)


def test_history_moves_likely_to_median_of_similar_tasks():
    history = [
        HistoricalMatch(project="A", title="x", task_type="backend", actual_hours=10, similarity=0.9),
        HistoricalMatch(project="B", title="y", task_type="backend", actual_hours=12, similarity=0.85),
        HistoricalMatch(project="C", title="z", task_type="backend", actual_hours=40, similarity=0.8),
        HistoricalMatch(
            project="D", title="w", task_type="backend", actual_hours=99, similarity=0.4
        ),  # poco similar
        HistoricalMatch(
            project="E", title="v", task_type="frontend", actual_hours=99, similarity=0.99
        ),  # otro tipo
    ]
    e = estimate_task(task("T1"), TASK_TYPES["backend"], history, 0)
    assert e.likely == 12
    assert e.pessimistic == 40  # el histórico amplía el rango
    assert len(e.historical_refs) == 3


def test_totals_sum_variances_and_commit_prudent_value():
    es = [estimate_task(task(f"T{i}"), TASK_TYPES["backend"], [], 0) for i in range(4)]
    t = totals(es, risk_margin_pct=0)
    assert t.expected_hours == pytest.approx(sum(e.expected for e in es), abs=0.1)
    assert t.p80_hours > t.expected_hours
    assert t.committed_hours == t.p80_hours  # sin margen, manda el P80


def test_topological_order_respects_dependencies_and_is_stable():
    es = [est("T3", 1, ["T1"]), est("T1", 1), est("T2", 1), est("T4", 1, ["T3", "T2"])]
    order = [e.task.id for e in topological_order(es)]
    assert order == ["T1", "T3", "T2", "T4"]


def test_cycle_is_rejected():
    with pytest.raises(SchedulingError, match="circular"):
        topological_order([est("T1", 1, ["T2"]), est("T2", 1, ["T1"])])


def test_unknown_dependency_is_rejected():
    with pytest.raises(SchedulingError, match="does not exist"):
        topological_order([est("T1", 1, ["T9"])])


def test_sprints_respect_capacity():
    es = [est(f"T{i}", 40) for i in range(5)]
    sprints, warnings = plan_sprints(es, capacity_hours=100)
    assert [s.task_ids for s in sprints] == [["T0", "T1"], ["T2", "T3"], ["T4"]]
    assert all(s.planned_hours <= 100 for s in sprints)
    assert not warnings


def test_dependent_task_never_lands_before_its_dependency():
    # T2 cabría en el sprint 1, pero depende de T1, que está en el sprint 2
    es = [est("T0", 90), est("T1", 50, ["T0"]), est("T2", 5, ["T1"])]
    sprints, _ = plan_sprints(es, capacity_hours=100)
    where = {tid: s.number for s in sprints for tid in s.task_ids}
    assert where["T0"] == 1
    assert where["T1"] == 2
    assert where["T2"] >= where["T1"]


def test_oversized_task_gets_own_sprint_and_warning():
    sprints, warnings = plan_sprints([est("T1", 10), est("BIG", 250)], capacity_hours=100)
    assert len(sprints) == 2
    assert sprints[1].task_ids == ["BIG"]
    assert "BIG" in warnings[0]
