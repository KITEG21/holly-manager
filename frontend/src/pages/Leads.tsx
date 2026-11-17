import { useQuery } from "@tanstack/react-query";
import { ExternalLink, Users } from "lucide-react";
import { Link } from "react-router-dom";
import { api, STAGE_LABEL, type Lead } from "../api";
import { Avatar, Badge, Card, EmptyState, PageHeader, Progress, Spinner, type Tone } from "../components/ui";

const STAGE_TONE: Record<Lead["stage"], Tone> = {
  qualification: "slate",
  requirements: "indigo",
  estimating: "amber",
  commercial: "blue",
  closed: "green",
  nurture: "amber",
  discarded: "red",
};

export default function Leads() {
  const leads = useQuery({ queryKey: ["leads"], queryFn: () => api<Lead[]>("/api/leads"), refetchInterval: 5000 });

  return (
    <>
      <PageHeader title="Clients" description="Who has talked to the agents, which stage they are in and how they score." />
      {leads.isLoading ? (
        <Spinner />
      ) : !leads.data?.length ? (
        <EmptyState icon={<Users />} title="No clients yet">
          Clients sign up from the sign-in screen.
        </EmptyState>
      ) : (
        <Card padded={false}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="border-b border-zinc-100 text-left text-xs text-zinc-500">
                  <th className="px-5 py-3 font-medium">Client</th>
                  <th className="px-3 py-3 font-medium">Stage</th>
                  <th className="px-3 py-3 font-medium">Qualification</th>
                  <th className="px-3 py-3 font-medium">Joined</th>
                  <th className="px-5 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {leads.data.map((l) => (
                  <tr key={l.id} className="hover:bg-zinc-50/60">
                    <td className="px-5 py-3">
                      <Link to={`/admin/leads/${l.id}`} className="flex items-center gap-3">
                        <Avatar name={l.name} />
                        <div>
                          <div className="font-medium text-zinc-900 hover:underline">{l.name}</div>
                          <div className="text-xs text-zinc-500">{l.email}</div>
                        </div>
                      </Link>
                    </td>
                    <td className="px-3 py-3">
                      <Badge tone={STAGE_TONE[l.stage]} dot>
                        {STAGE_LABEL[l.stage]}
                      </Badge>
                    </td>
                    <td className="px-3 py-3">
                      {l.qualification_score != null ? (
                        <div className="flex items-center gap-2">
                          <Progress className="w-20" value={l.qualification_score} max={100} tone={l.qualification_score >= 70 ? "success" : "brand"} />
                          <span className="text-xs tabular-nums text-zinc-600">{l.qualification_score.toFixed(0)}</span>
                        </div>
                      ) : (
                        <span className="text-zinc-400">—</span>
                      )}
                    </td>
                    <td className="px-3 py-3 text-xs text-zinc-500">{new Date(l.created_at).toLocaleDateString("en-US", { day: "numeric", month: "short" })}</td>
                    <td className="px-5 py-3 text-right">
                      <a className="inline-flex items-center gap-1 text-xs font-medium text-brand-700 hover:underline" href={`/chat/${l.id}`} target="_blank">
                        View chat <ExternalLink className="size-3" />
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </>
  );
}
