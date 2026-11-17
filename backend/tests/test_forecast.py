import pytest

from app.domain.forecast import TaskProgress, forecast_project


def t(key: str, planned: float, actual: float = 0, status: str = "todo") -> TaskProgress:
    return TaskProgress(key=key, planned_hours=planned, actual_hours=actual, status=status)


def test_without_closed_tasks_the_plan_holds():
    f = forecast_project(
        [t("T1", 10), t("T2", 20)], committed_hours=30, sprint_capacity_hours=20, alert_pct=10
    )
    assert f.performance_ratio == 1
    assert f.forecast_hours == 30
    assert f.deviation_pct == 0
    assert f.remaining_sprints == 2
    assert not f.alert


def test_observed_pace_is_projected_on_pending_tasks():
    # T1 costó un 50% más de lo previsto → T2 y T3 también se proyectan un 50% más largas
    tasks = [t("T1", 10, 15, "done"), t("T2", 20, 5, "in_progress"), t("T3", 10)]
    f = forecast_project(tasks, committed_hours=40, sprint_capacity_hours=100, alert_pct=10)
    assert f.performance_ratio == 1.5
    assert f.logged_hours == 20
    assert f.remaining_hours == pytest.approx(30 - 5 + 15)
    assert f.forecast_hours == 60
    assert f.deviation_pct == 50
    assert f.alert
    assert "50%" in f.alert_message


def test_faster_team_reduces_forecast():
    tasks = [t("T1", 10, 5, "done"), t("T2", 10)]
    f = forecast_project(tasks, committed_hours=20, sprint_capacity_hours=100, alert_pct=10)
    assert f.forecast_hours == 10
    assert f.deviation_pct == -50
    assert not f.alert


def test_overrun_in_progress_task_counts_hours_already_spent():
    f = forecast_project(
        [t("T1", 10, 18, "in_progress")], committed_hours=10, sprint_capacity_hours=100, alert_pct=10
    )
    assert f.remaining_hours == 0
    assert f.forecast_hours == 18
    assert f.alert
