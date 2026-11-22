import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ChevronLeft, Gauge, Hourglass, Layers, TrendingUp } from "lucide-react";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../../api";
import { Badge, Card, cx, errorMessage, PageHeader, Progress, Segmented, Select, Spinner, StatCard, useToast } from "../../components/ui";
import { TaskCard, TaskRow } from "../../components/work";
import ProjectDocs from "./ProjectDocs";
import { hours, STATUS_LABEL, STATUS_TONE, STATUSES, useTaskActions, type ProjectDetail, type Status, type Task } from "../../dev";

type View = "board" | "sprints" | "forecast" | "docs";
const VIEWS: View[] = ["board", "sprints", "forecast", "docs"];

export default function Project() {
  const leadId = Number(useParams().leadId);
  // La vista va en la URL para que las citas del asistente puedan enlazar a un documento del proyecto
  const [params, setParams] = useSearchParams();
  const view: View = VIEWS.includes(params.get("view") as View) ? (params.get("view") as View) : "board";
  const setView = (v: View) => setParams(v === "board" ? {} : { view: v });
  const [sprint, setSprint] = useState<number | "all">("all");
  const q = useQuery({ queryKey: ["dev-project", leadId], queryFn: () => api<ProjectDetail>(`/api/dev/projects/${leadId}`) });
  const p = q.data;

  return (
    <>
      <Link to="/dev/projects" className="mb-3 inline-flex items-center gap-1 text-xs font-medium text-zinc-500 hover:text-zinc-800">
        <ChevronLeft className="size-3.5" /> Projects
      </Link>
      {!p ? (
        <Spinner />
      ) : (
        <>
          <PageHeader
            title={p.name}
            description={`${p.forecast.total_tasks} tasks in ${p.sprints.length} sprints of ${p.sprint_weeks} weeks`}
            actions={
              <Segmented
                value={view}
                onChange={setView}
                options={[
                  { value: "board", label: "Board" },
                  { value: "sprints", label: "Sprints" },
                  { value: "forecast", label: "Forecast" },
                  { value: "docs", label: "Docs" },
                ]}
              />
            }
          />
          {p.forecast.alert && (
            <div className="mb-6 flex items-start gap-3 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-800 ring-1 ring-rose-200">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" />
              {p.forecast.alert_message}
            </div>
          )}
          {view === "board" && (
            <>
              <div className="mb-4">
                <div className="w-44">
                <Select className="h-9 py-1.5" value={sprint} onChange={(e) => setSprint(e.target.value === "all" ? "all" : Number(e.target.value))}>
                  <option value="all">All sprints</option>
                  {p.sprints.map((s) => (
                    <option key={s.number} value={s.number}>
                      Sprint {s.number}
                    </option>
                  ))}
                </Select>
                </div>
              </div>
              <Board tasks={p.sprints.filter((s) => sprint === "all" || s.number === sprint).flatMap((s) => s.tasks)} />
            </>
          )}
          {view === "sprints" && <Sprints project={p} />}
          {view === "forecast" && <ForecastView project={p} />}
          {view === "docs" && <ProjectDocs leadId={leadId} />}
        </>
      )}
    </>
  );
}

function Board({ tasks }: { tasks: Task[] }) {
  const { setStatus } = useTaskActions();
  const toast = useToast();
  const [over, setOver] = useState<Status | null>(null);

  async function drop(status: Status, e: React.DragEvent) {
    e.preventDefault();
    setOver(null);
    const id = Number(e.dataTransfer.getData("text/task"));
    const task = tasks.find((t) => t.id === id);
    if (!task || task.status === status) return;
    try {
      await setStatus.mutateAsync({ id, status });
      toast(`${task.key} → ${STATUS_LABEL[status]}`, "success");
    } catch (err) {
      toast(errorMessage(err), "error");
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      {STATUSES.map((s) => {
        const col = tasks.filter((t) => t.status === s);
        return (
          <div
            key={s}
            onDragOver={(e) => {
              e.preventDefault();
              setOver(s);
            }}
            onDragLeave={() => setOver((o) => (o === s ? null : o))}
            onDrop={(e) => drop(s, e)}
            className={cx(
              "flex min-h-64 flex-col rounded-2xl bg-zinc-100/70 p-3 ring-1 ring-transparent transition",
              over === s && "bg-brand-50 ring-brand-300",
            )}
          >
            <div className="mb-3 flex items-center justify-between px-1">
              <Badge tone={STATUS_TONE[s]} dot>
                {STATUS_LABEL[s]}
              </Badge>
              <span className="text-xs text-zinc-500 tabular-nums">
                {col.length} · {hours(col.reduce((a, t) => a + t.planned_hours, 0))}
              </span>
            </div>
            <div className="flex flex-1 flex-col gap-2">
              {col.map((t) => (
                <TaskCard key={t.id} task={t} draggable />
              ))}
              {col.length === 0 && <p className="py-8 text-center text-xs text-zinc-400">Drag tasks here</p>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Sprints({ project: p }: { project: ProjectDetail }) {
  return (
    <div className="space-y-4">
      {p.sprints.map((s) => {
        const done = s.tasks.filter((t) => t.status === "done").length;
        return (
          <Card
            key={s.number}
            title={`Sprint ${s.number}`}
            description={`${done}/${s.tasks.length} tasks done`}
            actions={
              <div className="w-40">
                <div className="mb-1 text-right text-xs text-zinc-500 tabular-nums">
                  {hours(s.actual_hours)} / {hours(s.planned_hours)}
                </div>
                <Progress value={s.actual_hours} max={s.planned_hours} tone={s.actual_hours > s.planned_hours ? "danger" : "brand"} />
              </div>
            }
            padded={false}
          >
            <div className="divide-y divide-zinc-100">
              {s.tasks.map((t) => (
                <TaskRow key={t.id} task={t} />
              ))}
            </div>
          </Card>
        );
      })}
    </div>
  );
}

function ForecastView({ project: p }: { project: ProjectDetail }) {
  const f = p.forecast;
  const max = Math.max(f.committed_hours, f.forecast_hours);
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard icon={<Layers />} label="Committed" value={hours(f.committed_hours)} hint="What was sold to the client" />
        <StatCard icon={<Hourglass />} label="Logged" value={hours(f.logged_hours)} hint={`${hours(f.remaining_hours)} forecast remaining`} />
        <StatCard
          icon={<TrendingUp />}
          label="Total forecast"
          value={hours(f.forecast_hours)}
          hint={`${f.deviation_pct > 0 ? "+" : ""}${f.deviation_pct}% vs. committed`}
          tone={f.alert ? "danger" : f.deviation_pct <= 0 ? "success" : "default"}
        />
        <StatCard
          icon={<Gauge />}
          label="Actual pace / plan"
          value={`×${f.performance_ratio}`}
          hint={`${f.remaining_sprints} sprints (${f.remaining_sprints * p.sprint_weeks} weeks) to go`}
        />
      </div>
      <Card title="Committed vs. forecast" description="The forecast applies the pace of closed tasks to the open ones.">
        <div className="space-y-4">
          {[
            { label: "Committed", value: f.committed_hours, cls: "bg-zinc-400" },
            { label: "Logged", value: f.logged_hours, cls: "bg-brand-500" },
            { label: "Total forecast", value: f.forecast_hours, cls: f.alert ? "bg-rose-500" : "bg-brand-500" },
          ].map((row) => (
            <div key={row.label} className="grid grid-cols-[120px_1fr_70px] items-center gap-3 text-sm">
              <span className="text-zinc-600">{row.label}</span>
              <div className="h-3 rounded-full bg-zinc-100">
                <div className={cx("h-3 rounded-full", row.cls)} style={{ width: `${max ? (row.value / max) * 100 : 0}%` }} />
              </div>
              <span className="text-right font-medium tabular-nums">{hours(row.value)}</span>
            </div>
          ))}
        </div>
        <p className="mt-5 text-xs text-zinc-500">
          {f.done_tasks === 0
            ? "No tasks closed yet: the forecast follows the plan."
            : `Based on ${f.done_tasks} closed tasks. With few tasks the pace varies a lot; it becomes more reliable as more are closed.`}
        </p>
      </Card>
    </div>
  );
}
