import { useQuery } from "@tanstack/react-query";
import { BarChart3 } from "lucide-react";
import { useState } from "react";
import { api } from "../../api";
import { DataTable, Legend, PairedBars, SERIES, StackedColumns } from "../../components/charts";
import { Badge, Card, EmptyState, PageHeader, Segmented, Spinner } from "../../components/ui";
import { hours, parseDate, TYPE_LABEL, type Reports as ReportsData } from "../../dev";

type Mode = "chart" | "table";
const OTHERS = "Others";

export default function Reports() {
  const [weeks, setWeeks] = useState<"4" | "8" | "12">("8");
  const q = useQuery({ queryKey: ["reports", weeks], queryFn: () => api<ReportsData>(`/api/dev/reports?weeks=${weeks}`) });
  const r = q.data;

  return (
    <>
      <PageHeader
        title="Reports"
        description="Team effort and estimation accuracy."
        actions={
          <Segmented
            value={weeks}
            onChange={setWeeks}
            options={[
              { value: "4", label: "4 weeks" },
              { value: "8", label: "8 weeks" },
              { value: "12", label: "12 weeks" },
            ]}
          />
        }
      />
      {!r ? (
        <Spinner />
      ) : (
        <div className="space-y-6">
          <div className="grid gap-6 xl:grid-cols-2">
            <WeeklyHours data={r} />
            <Accuracy data={r} />
          </div>
          <ProjectsTable data={r} />
        </div>
      )}
    </>
  );
}

function ModeToggle({ mode, setMode }: { mode: Mode; setMode: (m: Mode) => void }) {
  return (
    <Segmented
      value={mode}
      onChange={setMode}
      options={[
        { value: "chart", label: "Chart" },
        { value: "table", label: "Table" },
      ]}
    />
  );
}

function WeeklyHours({ data }: { data: ReportsData }) {
  const [mode, setMode] = useState<Mode>("chart");
  // Orden fijo por horas totales; a partir de la tercera persona se agrupa en «Otros»
  const totals = new Map<string, number>();
  for (const w of data.weekly_hours) totals.set(w.user, (totals.get(w.user) ?? 0) + w.hours);
  const ranked = [...totals.entries()].sort((a, b) => b[1] - a[1]).map(([u]) => u);
  const people = ranked.length > 3 ? [...ranked.slice(0, 2), OTHERS] : ranked;
  const series = people.map((label, i) => ({ label, color: SERIES[i]! }));
  const values = data.weeks.map((w) =>
    people.map((p) =>
      data.weekly_hours
        .filter((x) => x.week_start === w && (p === OTHERS ? !people.slice(0, 2).includes(x.user) : x.user === p))
        .reduce((a, x) => a + x.hours, 0),
    ),
  );
  const labels = data.weeks.map((w) => parseDate(w).toLocaleDateString("en-US", { day: "numeric", month: "short" }));

  return (
    <Card title="Hours logged per week" description="Per person, weeks from Monday to Sunday" actions={<ModeToggle mode={mode} setMode={setMode} />}>
      {totals.size === 0 ? (
        <EmptyState icon={<BarChart3 />} title="No hours in this period" />
      ) : mode === "chart" ? (
        <div className="space-y-4">
          {series.length > 1 && <Legend items={series} />}
          <StackedColumns categories={labels} series={series} values={values} format={(v) => `${Math.round(v * 10) / 10} h`} />
        </div>
      ) : (
        <DataTable
          head={["Week", ...people, "Total"]}
          rows={values.map((row, i) => [labels[i], ...row.map((v) => hours(v)), hours(row.reduce((a, b) => a + b, 0))])}
        />
      )}
    </Card>
  );
}

function Accuracy({ data }: { data: ReportsData }) {
  const [mode, setMode] = useState<Mode>("chart");
  const series: [{ label: string; color: string }, { label: string; color: string }] = [
    { label: "Planned", color: SERIES[0]! },
    { label: "Actual", color: SERIES[1]! },
  ];
  const ratioBadge = (ratio: number) => (
    <Badge tone={ratio > 1.15 ? "red" : ratio < 0.85 ? "blue" : "green"}>×{ratio.toFixed(2)}</Badge>
  );
  return (
    <Card
      title="Estimation accuracy by type"
      description="Closed tasks: planned vs. actual hours (×1 = exact)"
      actions={<ModeToggle mode={mode} setMode={setMode} />}
    >
      {data.accuracy_by_type.length === 0 ? (
        <EmptyState icon={<BarChart3 />} title="No closed tasks yet">
          As tasks are closed you'll see which kinds of work get underestimated.
        </EmptyState>
      ) : mode === "chart" ? (
        <div className="space-y-4">
          <Legend items={series} />
          <PairedBars
            series={series}
            format={hours}
            rows={data.accuracy_by_type.map((a) => ({
              label: `${TYPE_LABEL[a.task_type] ?? a.task_type} (${a.tasks})`,
              values: [a.planned_hours, a.actual_hours],
              extra: ratioBadge(a.ratio),
            }))}
          />
        </div>
      ) : (
        <DataTable
          head={["Type", "Tasks", "Planned", "Actual", "Actual / plan"]}
          rows={data.accuracy_by_type.map((a) => [
            TYPE_LABEL[a.task_type] ?? a.task_type,
            a.tasks,
            hours(a.planned_hours),
            hours(a.actual_hours),
            `×${a.ratio.toFixed(2)}`,
          ])}
        />
      )}
    </Card>
  );
}

function ProjectsTable({ data }: { data: ReportsData }) {
  return (
    <Card title="Projects" description="Hours committed to the client vs. the current forecast">
      {data.projects.length === 0 ? (
        <p className="text-sm text-zinc-500">No projects.</p>
      ) : (
        <DataTable
          head={["Project", "Progress", "Committed", "Logged", "Forecast", "Deviation"]}
          rows={data.projects.map((p) => {
            const f = p.forecast;
            return [
              p.name,
              `${f.done_tasks}/${f.total_tasks}`,
              hours(f.committed_hours),
              hours(f.logged_hours),
              hours(f.forecast_hours),
              <Badge key="d" tone={f.alert ? "red" : f.deviation_pct > 0 ? "amber" : "green"} dot>
                {f.deviation_pct > 0 ? "+" : ""}
                {f.deviation_pct}%
              </Badge>,
            ];
          })}
        />
      )}
    </Card>
  );
}
