import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, post, type Escalation } from "../api";
import { Badge, Button, Card, ErrorText } from "../components/ui";

export default function Escalations() {
  const [filter, setFilter] = useState<"open" | "">("open");
  const list = useQuery({
    queryKey: ["escalations", filter],
    queryFn: () => api<Escalation[]>(`/api/escalations${filter ? `?status=${filter}` : ""}`),
    refetchInterval: 5000,
  });
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">Escalated to a person</h1>
        <select
          className="rounded-lg border border-zinc-300 px-2 py-1 text-sm"
          value={filter}
          onChange={(e) => setFilter(e.target.value as "open" | "")}
        >
          <option value="open">Open</option>
          <option value="">All</option>
        </select>
      </div>
      {list.data?.length === 0 && <p className="text-sm text-zinc-500">No escalations.</p>}
      {list.data?.map((e) => <EscalationCard key={e.id} e={e} />)}
    </div>
  );
}

function EscalationCard({ e }: { e: Escalation }) {
  const qc = useQueryClient();
  const [reply, setReply] = useState("");
  const resolve = useMutation({
    mutationFn: () => post(`/api/escalations/${e.id}/resolve`, { reply_to_client: reply }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["escalations"] }),
  });
  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          #{e.id} · <Link className="text-brand-700 hover:underline" to={`/admin/leads/${e.lead_id}`}>{e.lead_name}</Link>
          <Badge tone={e.status === "open" ? "amber" : "green"}>{e.status === "open" ? "open" : "resolved"}</Badge>
        </span>
      }
    >
      <dl className="grid gap-1 text-sm md:grid-cols-[160px_1fr]">
        <dt className="text-zinc-500">Reason</dt>
        <dd>{e.reason}</dd>
        <dt className="text-zinc-500">Client request</dt>
        <dd className="italic">“{e.client_request}”</dd>
        {e.violations.length > 0 && (
          <>
            <dt className="text-zinc-500">Rules</dt>
            <dd>
              {e.violations.map((v, i) => (
                <div key={i} className="text-rose-700">
                  {v.code}: requested {v.requested ?? "—"}, limit {v.limit ?? "—"}
                </div>
              ))}
            </dd>
          </>
        )}
        {e.resolution && (
          <>
            <dt className="text-zinc-500">Reply</dt>
            <dd>{e.resolution}</dd>
          </>
        )}
      </dl>
      {e.status === "open" && (
        <div className="mt-3 space-y-2">
          <textarea
            className="w-full rounded-lg border border-zinc-300 p-2 text-sm"
            rows={3}
            placeholder="Reply the client will see in the chat…"
            value={reply}
            onChange={(ev) => setReply(ev.target.value)}
          />
          <Button onClick={() => resolve.mutate()} disabled={!reply.trim() || resolve.isPending}>
            Reply and close
          </Button>
          <ErrorText error={resolve.error} />
        </div>
      )}
    </Card>
  );
}
