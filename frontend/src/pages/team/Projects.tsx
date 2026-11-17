import { useQuery } from "@tanstack/react-query";
import { FolderKanban } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../../api";
import { Badge, EmptyState, PageHeader, Progress, Spinner } from "../../components/ui";
import { hours, type ProjectSummary } from "../../dev";

export default function Projects() {
  const q = useQuery({ queryKey: ["dev-projects"], queryFn: () => api<ProjectSummary[]>("/api/dev/projects") });
  return (
    <>
      <PageHeader title="Projects" description="Confirmed projects with their backlog. They appear once the estimate is finished." />
      {q.isLoading ? (
        <Spinner />
      ) : !q.data?.length ? (
        <EmptyState icon={<FolderKanban />} title="No projects yet">
          When a client confirms their requirements and the estimate finishes, the backlog shows up here.
        </EmptyState>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {q.data.map((p) => {
            const f = p.forecast;
            const pct = f.total_tasks ? Math.round((f.done_tasks / f.total_tasks) * 100) : 0;
            return (
              <Link
                key={p.lead_id}
                to={`/dev/projects/${p.lead_id}`}
                className="group rounded-2xl bg-white p-5 shadow-card ring-1 ring-zinc-950/5 transition hover:-translate-y-0.5 hover:shadow-pop"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="grid size-10 place-items-center rounded-xl bg-brand-50 text-brand-700">
                    <FolderKanban className="size-5" />
                  </div>
                  {f.alert ? (
                    <Badge tone="red" dot>
                      Deviation {f.deviation_pct > 0 ? "+" : ""}
                      {f.deviation_pct}%
                    </Badge>
                  ) : (
                    <Badge tone="green" dot>
                      On track
                    </Badge>
                  )}
                </div>
                <h3 className="mt-4 font-semibold text-zinc-900 group-hover:text-brand-700">{p.name}</h3>
                <p className="mt-0.5 text-xs text-zinc-500">
                  {f.total_tasks} tasks · {f.remaining_sprints} sprints left
                </p>
                <div className="mt-5 flex items-baseline justify-between text-xs">
                  <span className="font-medium text-zinc-700">{pct}% complete</span>
                  <span className="text-zinc-500 tabular-nums">
                    {hours(f.logged_hours)} / {hours(f.committed_hours)}
                  </span>
                </div>
                <Progress className="mt-1.5" value={f.done_tasks} max={f.total_tasks} tone={f.alert ? "danger" : "brand"} />
              </Link>
            );
          })}
        </div>
      )}
    </>
  );
}
