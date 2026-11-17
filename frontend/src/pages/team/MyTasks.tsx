import { useQuery } from "@tanstack/react-query";
import { ListChecks, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../../api";
import { Card, EmptyState, PageHeader, Segmented, Select, Spinner } from "../../components/ui";
import { TaskRow } from "../../components/work";
import { STATUS_LABEL, STATUSES, type Status, type Task } from "../../dev";

type Scope = "mine" | "all" | "unassigned";

export default function MyTasks() {
  const [scope, setScope] = useState<Scope>("mine");
  const [status, setStatus] = useState<Status | "open">("open");
  const [project, setProject] = useState("");
  const [query, setQuery] = useState("");
  const q = useQuery({ queryKey: ["dev-tasks", "all"], queryFn: () => api<Task[]>("/api/dev/tasks") });
  const me = useQuery({ queryKey: ["dev-tasks", "mine"], queryFn: () => api<Task[]>("/api/dev/tasks?mine=true") });

  const projects = useMemo(() => [...new Set((q.data ?? []).map((t) => t.project))], [q.data]);
  const mineIds = new Set((me.data ?? []).map((t) => t.id));
  const tasks = (q.data ?? []).filter(
    (t) =>
      (scope === "all" || (scope === "mine" ? mineIds.has(t.id) : t.assignee_id == null)) &&
      (status === "open" ? t.status !== "done" : t.status === status) &&
      (!project || t.project === project) &&
      (!query || `${t.key} ${t.title}`.toLowerCase().includes(query.toLowerCase())),
  );
  const groups = STATUSES.map((s) => ({ status: s, tasks: tasks.filter((t) => t.status === s) })).filter((g) => g.tasks.length);

  return (
    <>
      <PageHeader title="My tasks" description="All assigned work, across every project." />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Segmented
          value={scope}
          onChange={setScope}
          options={[
            { value: "mine", label: "Assigned to me" },
            { value: "unassigned", label: "Unassigned" },
            { value: "all", label: "All" },
          ]}
        />
        <div className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-zinc-400" />
          <input
            className="h-9 w-56 rounded-lg bg-white pr-3 pl-8 text-sm shadow-sm ring-1 ring-zinc-200 placeholder:text-zinc-400 focus:ring-2 focus:ring-brand-500 focus:outline-none"
            placeholder="Search tasks…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div className="w-40">
        <Select className="h-9 py-1.5" value={status} onChange={(e) => setStatus(e.target.value as Status | "open")}>
          <option value="open">Open</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABEL[s]}
            </option>
          ))}
        </Select>
        </div>
        {projects.length > 1 && (
          <div className="w-48">
          <Select className="h-9 py-1.5" value={project} onChange={(e) => setProject(e.target.value)}>
            <option value="">All projects</option>
            {projects.map((p) => (
              <option key={p}>{p}</option>
            ))}
          </Select>
          </div>
        )}
      </div>

      {q.isLoading ? (
        <Spinner />
      ) : groups.length === 0 ? (
        <EmptyState icon={<ListChecks />} title="Nothing here">
          {scope === "mine" ? "You have no tasks matching these filters. Try \"Unassigned\" to pick one up." : "No tasks match these filters."}
        </EmptyState>
      ) : (
        <div className="space-y-4">
          {groups.map((g) => (
            <Card key={g.status} title={`${STATUS_LABEL[g.status]} · ${g.tasks.length}`} padded={false}>
              <div className="divide-y divide-zinc-100">
                {g.tasks.map((t) => (
                  <TaskRow key={t.id} task={t} showProject />
                ))}
              </div>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
