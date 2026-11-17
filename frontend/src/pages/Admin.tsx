import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { api, put } from "../api";
import { Badge, Button, Card, ErrorText, Input, PageHeader } from "../components/ui";

interface TaskType {
  name: string;
  min_hours: number;
  max_hours: number;
  complexity: "low" | "medium" | "high";
}
interface Team {
  members: number;
  capacity_hours_per_sprint: number;
  velocity_factor: number;
  sprint_weeks: number;
  deviation_alert_pct: number;
}
interface Commercial {
  currency: string;
  hourly_rate: string;
  min_price: string;
  max_discount_pct: string;
  deposit_pct: string;
  milestones: { name: string; pct: string }[];
  included_change_rounds: number;
  support_months: number;
  max_scope_hours: number;
  risk_margin_pct: number;
}
interface Qualification {
  thresholds: { qualified: number; nurture: number; min_timeline_weeks: number };
  criteria: { key: string; question: string; weight: number; enabled: boolean }[];
}
interface Doc {
  id: number;
  filename: string;
  kind: string;
  status: string;
  error: string | null;
  chunk_count: number;
}

/** Formulario ligado a un recurso GET/PUT: la validación de verdad la hace Pydantic en el servidor. */
function useResource<T>(path: string) {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: [path], queryFn: () => api<T>(path) });
  const [draft, setDraft] = useState<T | null>(null);
  useEffect(() => {
    if (query.data) setDraft(query.data);
  }, [query.data]);
  const save = useMutation({
    mutationFn: (value: T) => put<T>(path, value),
    onSuccess: () => qc.invalidateQueries({ queryKey: [path] }),
  });
  return { draft, setDraft, save };
}

function SaveBar({ onSave, pending, error, saved }: { onSave: () => void; pending: boolean; error: unknown; saved: boolean }) {
  return (
    <div className="mt-3 flex items-center gap-3">
      <Button onClick={onSave} disabled={pending}>
        Save
      </Button>
      {saved && !error && <span className="text-xs text-emerald-700">Saved</span>}
      <ErrorText error={error} />
    </div>
  );
}

const num = (v: string) => (v === "" ? 0 : Number(v));

export default function Admin() {
  return (
    <>
    <PageHeader title="Settings" description="Every number the agents and the estimate use comes from here." />
    <div className="grid gap-6 lg:grid-cols-2">
      <TaskTypes />
      <TeamForm />
      <CommercialForm />
      <QualificationForm />
      <Documents />
    </div>
    </>
  );
}

function TaskTypes() {
  const { draft, setDraft, save } = useResource<TaskType[]>("/api/admin/task-types");
  if (!draft) return null;
  const update = (i: number, patch: Partial<TaskType>) => setDraft(draft.map((t, j) => (i === j ? { ...t, ...patch } : t)));
  return (
    <Card title="Task types" actions={<Button variant="secondary" onClick={() => setDraft([...draft, { name: "", min_hours: 1, max_hours: 8, complexity: "medium" }])}>Add</Button>}>
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-zinc-500">
          <tr>
            <th>Type</th>
            <th>Min h</th>
            <th>Max h</th>
            <th>Complexity</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {draft.map((t, i) => (
            <tr key={i}>
              <td className="pr-2">
                <Input value={t.name} onChange={(e) => update(i, { name: e.target.value })} />
              </td>
              <td className="pr-2">
                <Input type="number" value={t.min_hours} onChange={(e) => update(i, { min_hours: num(e.target.value) })} />
              </td>
              <td className="pr-2">
                <Input type="number" value={t.max_hours} onChange={(e) => update(i, { max_hours: num(e.target.value) })} />
              </td>
              <td className="pr-2">
                <select
                  className="rounded-lg border border-zinc-300 px-2 py-1.5 text-sm"
                  value={t.complexity}
                  onChange={(e) => update(i, { complexity: e.target.value as TaskType["complexity"] })}
                >
                  <option value="low">low</option>
                  <option value="medium">medium</option>
                  <option value="high">high</option>
                </select>
              </td>
              <td>
                <Button variant="secondary" onClick={() => setDraft(draft.filter((_, j) => j !== i))}>
                  ✕
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <SaveBar onSave={() => save.mutate(draft)} pending={save.isPending} error={save.error} saved={save.isSuccess} />
    </Card>
  );
}

function Grid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-2 gap-3">{children}</div>;
}

function TeamForm() {
  const { draft, setDraft, save } = useResource<Team>("/api/admin/team");
  if (!draft) return null;
  const field = (key: keyof Team, label: string, step = "1") => (
    <Input label={label} type="number" step={step} value={draft[key]} onChange={(e) => setDraft({ ...draft, [key]: num(e.target.value) })} />
  );
  return (
    <Card title="Team">
      <Grid>
        {field("members", "People")}
        {field("capacity_hours_per_sprint", "Capacity per sprint (h)")}
        {field("velocity_factor", "Velocity (fraction delivered)", "0.05")}
        {field("sprint_weeks", "Sprint length (weeks)")}
        {field("deviation_alert_pct", "Deviation alert (%)")}
      </Grid>
      <p className="mt-2 text-xs text-zinc-500">
        Effective capacity: {(draft.capacity_hours_per_sprint * draft.velocity_factor).toFixed(0)} h per sprint
      </p>
      <SaveBar onSave={() => save.mutate(draft)} pending={save.isPending} error={save.error} saved={save.isSuccess} />
    </Card>
  );
}

function CommercialForm() {
  const { draft, setDraft, save } = useResource<Commercial>("/api/admin/commercial");
  if (!draft) return null;
  const text = (key: keyof Commercial, label: string) => (
    <Input label={label} value={String(draft[key])} onChange={(e) => setDraft({ ...draft, [key]: e.target.value })} />
  );
  const number = (key: keyof Commercial, label: string) => (
    <Input label={label} type="number" value={Number(draft[key])} onChange={(e) => setDraft({ ...draft, [key]: num(e.target.value) })} />
  );
  return (
    <Card title="Reglas comerciales">
      <Grid>
        {text("hourly_rate", "Hourly rate (€/h)")}
        {text("min_price", "Minimum price (€)")}
        {text("max_discount_pct", "Maximum discount (%)")}
        {text("deposit_pct", "Deposit (%)")}
        {number("included_change_rounds", "Included change rounds")}
        {number("support_months", "Months of support")}
        {number("max_scope_hours", "Maximum scope (h)")}
        {number("risk_margin_pct", "Risk margin (%)")}
      </Grid>
      <div className="mt-3">
        <div className="mb-1 text-xs font-medium text-zinc-600">Milestone payments (deposit + milestones = 100%)</div>
        {draft.milestones.map((m, i) => (
          <div key={i} className="mb-2 flex gap-2">
            <Input value={m.name} onChange={(e) => setDraft({ ...draft, milestones: draft.milestones.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)) })} />
            <Input className="w-24" value={m.pct} onChange={(e) => setDraft({ ...draft, milestones: draft.milestones.map((x, j) => (j === i ? { ...x, pct: e.target.value } : x)) })} />
            <Button variant="secondary" onClick={() => setDraft({ ...draft, milestones: draft.milestones.filter((_, j) => j !== i) })}>
              ✕
            </Button>
          </div>
        ))}
        <Button variant="secondary" onClick={() => setDraft({ ...draft, milestones: [...draft.milestones, { name: "New milestone", pct: "0" }] })}>
          Add milestone
        </Button>
      </div>
      <SaveBar onSave={() => save.mutate(draft)} pending={save.isPending} error={save.error} saved={save.isSuccess} />
    </Card>
  );
}

const CRITERION_LABEL: Record<string, string> = {
  budget: "Budget",
  timeline: "Timeline",
  decision_maker: "Decision maker",
  company: "Company",
  corporate_email: "Company email",
  need_clarity: "Need clarity",
};

function QualificationForm() {
  const { draft, setDraft, save } = useResource<Qualification>("/api/admin/qualification");
  if (!draft) return null;
  const totalWeight = draft.criteria.filter((c) => c.enabled).reduce((a, c) => a + c.weight, 0);
  const setTh = (key: keyof Qualification["thresholds"], v: string) =>
    setDraft({ ...draft, thresholds: { ...draft.thresholds, [key]: num(v) } });
  const setCrit = (i: number, patch: Partial<Qualification["criteria"][number]>) =>
    setDraft({ ...draft, criteria: draft.criteria.map((c, j) => (i === j ? { ...c, ...patch } : c)) });
  return (
    <Card title="Qualification">
      <div className="grid grid-cols-3 gap-3">
        <Input label="Qualified threshold" type="number" value={draft.thresholds.qualified} onChange={(e) => setTh("qualified", e.target.value)} />
        <Input label="Nurture threshold" type="number" value={draft.thresholds.nurture} onChange={(e) => setTh("nurture", e.target.value)} />
        <Input label="Minimum timeline (weeks)" type="number" value={draft.thresholds.min_timeline_weeks} onChange={(e) => setTh("min_timeline_weeks", e.target.value)} />
      </div>
      <div className="mt-3 space-y-2">
        {draft.criteria.map((c, i) => (
          <div key={c.key} className="grid grid-cols-[auto_1fr_80px] items-end gap-2">
            <label className="flex items-center gap-1 pb-2 text-xs">
              <input type="checkbox" checked={c.enabled} onChange={(e) => setCrit(i, { enabled: e.target.checked })} />
              <span className="w-32">{CRITERION_LABEL[c.key] ?? c.key}</span>
            </label>
            <Input value={c.question} onChange={(e) => setCrit(i, { question: e.target.value })} />
            <Input type="number" value={c.weight} onChange={(e) => setCrit(i, { weight: num(e.target.value) })} />
          </div>
        ))}
      </div>
      <p className="mt-2 text-xs text-zinc-500">Weights are normalised: current total {totalWeight}.</p>
      <SaveBar onSave={() => save.mutate(draft)} pending={save.isPending} error={save.error} saved={save.isSuccess} />
    </Card>
  );
}

function Documents() {
  const qc = useQueryClient();
  const docs = useQuery({ queryKey: ["docs"], queryFn: () => api<Doc[]>("/api/admin/documents"), refetchInterval: 4000 });
  const history = useQuery({ queryKey: ["historical"], queryFn: () => api<{ count: number; embedded: number }>("/api/admin/historical") });
  const [kind, setKind] = useState("contract");
  const [file, setFile] = useState<File | null>(null);
  const upload = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.append("kind", kind);
      fd.append("file", file!);
      return api<Doc>("/api/admin/documents", { method: "POST", body: fd });
    },
    onSuccess: () => {
      setFile(null);
      qc.invalidateQueries({ queryKey: ["docs"] });
    },
  });
  return (
    <Card title="Documents (Docling → pgvector)">
      <div className="flex flex-wrap items-center gap-2">
        <select className="rounded-lg border border-zinc-300 px-2 py-1.5 text-sm" value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="contract">Contract template</option>
          <option value="policy">Policy</option>
        </select>
        <input type="file" accept=".pdf,.docx,.md,.html,.txt,.pptx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-sm" />
        <Button onClick={() => upload.mutate()} disabled={!file || upload.isPending}>
          Upload
        </Button>
      </div>
      <ErrorText error={upload.error} />
      <ul className="mt-3 space-y-1 text-sm">
        {docs.data?.map((d) => (
          <li key={d.id} className="flex items-center gap-2">
            <Badge tone={d.status === "ready" ? "green" : d.status === "failed" ? "red" : "amber"}>{d.status}</Badge>
            <span>{d.filename}</span>
            <span className="text-xs text-zinc-500">
              {d.kind} · {d.chunk_count} chunks
            </span>
            {d.error && <span className="text-xs text-rose-600">{d.error}</span>}
          </li>
        ))}
      </ul>
      {history.data && (
        <p className="mt-3 text-xs text-zinc-500">
          Project history: {history.data.count} tasks with actual hours ({history.data.embedded} indexed).
        </p>
      )}
    </Card>
  );
}
