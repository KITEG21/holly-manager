import { useQuery } from "@tanstack/react-query";
import { Fragment } from "react";
import { useParams } from "react-router-dom";
import { api, formatMoney, JAEGER_URL, STAGE_LABEL, type EstimateResult, type LeadState, type Message } from "../api";
import { Badge, Card } from "../components/ui";

interface Qualification {
  explanation?: string;
  result?: { score: number; lines: { key: string; points: number; reason: string; quote: string | null }[] };
}

interface EstimateResponse {
  id: number;
  status: string;
  error: string | null;
  result: EstimateResult | null;
}

export default function LeadInternal() {
  const leadId = Number(useParams().leadId);
  const state = useQuery({
    queryKey: ["state", leadId],
    queryFn: () => api<LeadState>(`/api/leads/${leadId}/state`),
    refetchInterval: 5000,
  });
  const messages = useQuery({
    queryKey: ["internal-messages", leadId],
    queryFn: () => api<Message[]>(`/api/leads/${leadId}/internal/messages`),
    refetchInterval: 5000,
  });
  const qual = useQuery({
    queryKey: ["qualification", leadId],
    queryFn: () => api<Qualification>(`/api/leads/${leadId}/internal/qualification`),
    refetchInterval: 5000,
  });
  const estimate = useQuery({
    queryKey: ["estimate", leadId],
    queryFn: () => api<EstimateResponse>(`/api/leads/${leadId}/internal/estimate`),
    retry: false,
    refetchInterval: (q) => (q.state.data?.status === "done" || q.state.data?.status === "failed" ? false : 4000),
  });

  const lead = state.data?.lead;
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">{lead?.name}</h1>
        {lead && <Badge tone="indigo">{STAGE_LABEL[lead.stage]}</Badge>}
        <a className="text-sm text-brand-700 hover:underline" href={`/chat/${leadId}`} target="_blank">
          Open the client's chat
        </a>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Qualification">
          {qual.data?.result ? (
            <>
              <p className="mb-2 text-3xl font-bold">{qual.data.result.score.toFixed(0)}</p>
              <ul className="space-y-1 text-sm">
                {qual.data.result.lines.map((l) => (
                  <li key={l.key} className="flex justify-between gap-2">
                    <span>
                      {l.reason}
                      {l.quote && <span className="block text-xs italic text-zinc-500">“{l.quote}”</span>}
                    </span>
                    <span className="font-mono text-emerald-700">+{l.points.toFixed(0)}</span>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="text-sm text-zinc-500">No data yet.</p>
          )}
        </Card>

        <Card title="Conversation traceability">
          <div className="max-h-96 space-y-2 overflow-y-auto text-sm">
            {messages.data?.map((m) => (
              <div key={m.id} className="border-b border-zinc-100 pb-2">
                <div className="flex items-center gap-2 text-xs text-zinc-500">
                  <span className="font-mono">#{m.id}</span>
                  <Badge tone={m.role === "user" ? "slate" : m.role === "human" ? "green" : "indigo"}>
                    {m.role === "user" ? "client" : (m.agent ?? m.role)}
                  </Badge>
                  {m.meta?.trace_id && (
                    <a className="text-brand-700 hover:underline" href={`${JAEGER_URL}/trace/${m.meta.trace_id}`} target="_blank">
                      trace
                    </a>
                  )}
                </div>
                <p className="mt-1 whitespace-pre-wrap">{m.content}</p>
                {!!m.meta?.tool_calls?.length && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {m.meta.tool_calls.map((t, i) => (
                      <Badge key={i}>{t.name}</Badge>
                    ))}
                  </div>
                )}
                {m.meta?.violations?.map((v, i) => (
                  <div key={i} className="mt-1 text-xs text-rose-700">
                    ⚠ {v.code}: {v.message} {v.requested && `(requested ${v.requested}${v.limit ? `, limit ${v.limit}` : ""})`}
                  </div>
                ))}
                {m.meta?.citations?.map((c) => (
                  <div key={c.id} className="text-xs text-zinc-500">
                    [C{c.id}] {c.label}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </Card>
      </div>

      <EstimateView data={estimate.data} />
    </div>
  );
}

function EstimateView({ data }: { data?: EstimateResponse }) {
  if (!data) return null;
  if (data.status !== "done" || !data.result) {
    return (
      <Card title="Estimate (internal)">
        <p className="text-sm text-zinc-600">
          Status: {data.status} {data.error && <span className="text-rose-600">— {data.error}</span>}
        </p>
      </Card>
    );
  }
  const r = data.result;
  const byId = Object.fromEntries(r.tasks.map((t) => [t.task.id, t]));
  return (
    <Card title="Estimate and sprints (internal, never shown to the client)">
      <div className="mb-4 grid grid-cols-2 gap-3 text-sm md:grid-cols-5">
        <Stat label="Expected hours (PERT)" value={`${r.totals.expected_hours} h`} />
        <Stat label="P80" value={`${r.totals.p80_hours} h`} />
        <Stat label={`Committed (+${r.totals.risk_margin_pct}% risk)`} value={`${r.totals.committed_hours} h`} />
        <Stat label="Timeline" value={`${r.weeks} weeks · ${r.sprints.length} sprints`} />
        <Stat
          label={`List price${r.quote.min_price_applied ? " (minimum)" : ""}`}
          value={formatMoney(r.quote.list_price, r.quote.currency)}
        />
      </div>
      {r.scope_exceeds_max && <p className="mb-2 text-sm text-rose-700">The scope exceeds the maximum that can be committed: escalated.</p>}
      {r.warnings.map((w) => (
        <p key={w} className="text-sm text-amber-700">
          ⚠ {w}
        </p>
      ))}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {r.sprints.map((s) => (
          <div key={s.number} className="rounded-lg border border-zinc-200 p-3">
            <div className="mb-2 flex justify-between text-sm font-medium">
              <span>Sprint {s.number}</span>
              <span className="text-zinc-500">
                {s.planned_hours.toFixed(1)} / {s.capacity_hours} h
              </span>
            </div>
            <div className="mb-2 h-1.5 rounded bg-zinc-100">
              <div className="h-1.5 rounded bg-brand-500" style={{ width: `${Math.min(100, (s.planned_hours / s.capacity_hours) * 100)}%` }} />
            </div>
            <table className="w-full text-xs">
              <tbody>
                {s.task_ids.map((id) => {
                  const t = byId[id];
                  return (
                    <Fragment key={id}>
                      <tr className="border-t border-zinc-100" title={t.basis}>
                        <td className="py-1 font-mono text-brand-700">{id}</td>
                        <td>
                          {t.task.title}
                          <div className="text-zinc-400">
                            {t.task.story_id} · {t.task.task_type}
                            {t.task.depends_on.length > 0 && ` · after ${t.task.depends_on.join(", ")}`}
                          </div>
                        </td>
                        <td className="whitespace-nowrap text-right text-zinc-600">
                          {t.optimistic}/{t.likely}/{t.pessimistic}
                          <div className="font-medium text-zinc-800">{t.planned_hours} h</div>
                        </td>
                      </tr>
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        ))}
      </div>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-zinc-50 p-2">
      <div className="text-xs text-zinc-500">{label}</div>
      <div className="font-semibold">{value}</div>
    </div>
  );
}
