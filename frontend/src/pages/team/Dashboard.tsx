import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, CheckCircle2, Clock, Flame, ListTodo, Timer } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../../api";
import { useAuth } from "../../auth";
import { Avatar, Badge, Card, EmptyState, PageHeader, Progress, Spinner, StatCard } from "../../components/ui";
import { TaskRow, useTaskDrawer } from "../../components/work";
import { hours, parseDate, type Dashboard as DashboardData } from "../../dev";

function greeting() {
  const h = new Date().getHours();
  return h < 13 ? "Good morning" : h < 20 ? "Good afternoon" : "Good evening";
}

export default function Dashboard() {
  const { user } = useAuth();
  const { openTask } = useTaskDrawer();
  const q = useQuery({ queryKey: ["dashboard"], queryFn: () => api<DashboardData>("/api/dev/dashboard"), refetchInterval: 30_000 });
  const d = q.data;

  return (
    <>
      <PageHeader
        eyebrow="Your day"
        title={
          <>
            {greeting()}, <span className="text-brand-600">{user?.name.split(" ")[0] ?? ""}</span>
          </>
        }
        description="What you have on your plate and how the projects are going."
      />
      {!d ? (
        <Spinner />
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard icon={<Clock />} label="Today" value={hours(d.today_hours)} hint="Hours logged today" />
            <StatCard
              icon={<Timer />}
              label="This week"
              value={hours(d.week_hours)}
              hint={
                <span className="flex items-center gap-2">
                  <Progress className="w-20" value={d.week_hours} max={d.week_target_hours} /> target {hours(d.week_target_hours)}
                </span>
              }
            />
            <StatCard icon={<ListTodo />} label="My open tasks" value={d.my_open_tasks} hint={`${d.my_in_progress} in progress`} />
            <StatCard icon={<CheckCircle2 />} label="Closed by the team" value={d.team_done_this_week} hint="This week" tone="success" />
          </div>

          <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
            <Card
              title="My next tasks"
              description="In-progress work first"
              actions={
                <Link to="/dev/tasks" className="flex items-center gap-1 text-xs font-medium text-brand-700 hover:underline">
                  View all <ArrowRight className="size-3" />
                </Link>
              }
              padded={false}
            >
              {d.my_tasks.length === 0 ? (
                <div className="p-5">
                  <EmptyState icon={<ListTodo />} title="You have no assigned tasks">
                    Assign yourself one from a project, or start logging time on an unassigned task.
                  </EmptyState>
                </div>
              ) : (
                <div className="divide-y divide-zinc-100">
                  {d.my_tasks.map((t) => (
                    <TaskRow key={t.id} task={t} showProject />
                  ))}
                </div>
              )}
            </Card>

            <Card title="Project health" padded={false}>
              {d.projects.length === 0 ? (
                <p className="p-5 text-sm text-zinc-500">There are no projects with a backlog yet.</p>
              ) : (
                <ul className="divide-y divide-zinc-100">
                  {d.projects.map((p) => {
                    const f = p.forecast;
                    return (
                      <li key={p.lead_id}>
                        <Link to={`/dev/projects/${p.lead_id}`} className="block px-5 py-4 transition hover:bg-zinc-50">
                          <div className="flex items-center justify-between gap-2">
                            <span className="truncate text-sm font-medium">{p.name}</span>
                            {f.alert ? (
                              <Badge tone="red" dot>
                                <Flame className="size-3" /> {f.deviation_pct > 0 ? "+" : ""}
                                {f.deviation_pct}%
                              </Badge>
                            ) : (
                              <Badge tone="green" dot>
                                On track
                              </Badge>
                            )}
                          </div>
                          <Progress className="mt-2.5" value={f.done_tasks} max={f.total_tasks} tone={f.alert ? "danger" : "brand"} />
                          <div className="mt-1.5 flex justify-between text-xs text-zinc-500">
                            <span>
                              {f.done_tasks}/{f.total_tasks} tasks
                            </span>
                            <span className="tabular-nums">
                              {hours(f.logged_hours)} of {hours(f.committed_hours)}
                            </span>
                          </div>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              )}
            </Card>
          </div>

          <Card title="Recent team activity" padded={false}>
            {d.activity.length === 0 ? (
              <p className="p-5 text-sm text-zinc-500">No time has been logged yet.</p>
            ) : (
              <ul className="divide-y divide-zinc-100">
                {d.activity.map((a, i) => (
                  <li key={i}>
                    <button onClick={() => openTask(a.task_id)} className="flex w-full items-center gap-3 px-5 py-3 text-left hover:bg-zinc-50">
                      <Avatar name={a.user} size="sm" />
                      <p className="min-w-0 flex-1 truncate text-sm text-zinc-700">
                        <span className="font-medium text-zinc-900">{a.user}</span> logged{" "}
                        <span className="font-medium tabular-nums text-zinc-900">{hours(a.hours)}</span> on{" "}
                        <span className="font-mono text-xs text-brand-700">{a.key}</span> {a.title}
                        <span className="text-zinc-400"> · {a.project}</span>
                        {a.note && <span className="text-zinc-500"> — {a.note}</span>}
                      </p>
                      <span className="shrink-0 text-xs text-zinc-400">
                        {parseDate(a.work_date).toLocaleDateString("en-US", { day: "numeric", month: "short" })}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {d.projects.some((p) => p.forecast.alert) && (
            <p className="flex items-center gap-2 text-xs text-zinc-500">
              <AlertTriangle className="size-3.5 text-rose-500" /> Flagged projects have a forecast above the configured deviation
              threshold.
            </p>
          )}
        </div>
      )}
    </>
  );
}
