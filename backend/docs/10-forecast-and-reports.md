# Forecast and reports

## Forecast

Every time entry or status change recalculates the project forecast. The forecast uses deterministic code:

- **Pace** (performance ratio) = actual hours ÷ planned hours of the **closed** tasks. With no closed tasks, the pace is 1 and the forecast follows the plan.
- **Remaining hours** = for every open task, planned hours × pace − hours already logged on it (never below zero).
- **Forecast total** = hours logged + remaining hours.
- **Deviation** = (forecast total − committed hours) ÷ committed hours, as a percentage.
- **Sprints left** = remaining hours ÷ effective capacity per sprint, rounded up.

When the deviation is above the alert threshold (default 10%, **Settings → Team → Deviation alert**), the project is flagged: a red "Deviation" badge on the project card and the dashboard, and an alert like "The forecast (304 h) exceeds the committed hours (175 h) by 74%; the alert threshold is 10%."

With only one or two closed tasks the pace can swing a lot; the forecast becomes more reliable as more tasks are closed.

## Reports

**Reports** covers the last 4, 8 or 12 weeks. Every chart can be switched to a table.

| Report | What it shows |
|---|---|
| Hours logged per week | Hours per person per week (Monday to Sunday). From the fourth person on, people are grouped as "Others" |
| Estimation accuracy by type | For closed tasks: planned vs. actual hours per task type, and the ratio actual ÷ plan. Above ×1.15 (red) that type is being underestimated; below ×0.85 (blue) it is being overestimated |
| Projects | Progress, committed, logged and forecast hours, and the deviation per project |
