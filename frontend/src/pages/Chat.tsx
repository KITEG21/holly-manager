import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, Check, ChevronLeft, FileDown, FileText, LogOut } from "lucide-react";
import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { api, openProtectedFile, post, streamChat, type LeadState, type Message, type RequirementDoc, type Stage } from "../api";
import { useAuth } from "../auth";
import RequirementDocView from "../components/RequirementDocView";
import { HollyMark, Logo } from "../components/Shell";
import { Avatar, Badge, Button, cx, ErrorText } from "../components/ui";

const SHOW_DOC = new Set<Stage>(["requirements", "estimating", "commercial", "closed"]);

const STEPS: { label: string; stages: Stage[] }[] = [
  { label: "Get to know you", stages: ["qualification", "nurture", "discarded"] },
  { label: "Requirements", stages: ["requirements"] },
  { label: "Estimate", stages: ["estimating"] },
  { label: "Proposal", stages: ["commercial", "closed"] },
];

function Stepper({ stage }: { stage?: Stage }) {
  const current = stage ? STEPS.findIndex((s) => s.stages.includes(stage)) : 0;
  return (
    <ol className="hidden items-center gap-2 md:flex">
      {STEPS.map((s, i) => (
        <Fragment key={s.label}>
          {i > 0 && <span className={cx("h-px w-6", i <= current ? "bg-brand-400" : "bg-zinc-200")} />}
          <li className="flex items-center gap-2 text-xs font-medium">
            <span
              className={cx(
                "grid size-5 place-items-center rounded-full text-[10px]",
                i < current ? "bg-brand-600 text-white" : i === current ? "bg-brand-100 text-brand-700 ring-1 ring-brand-300" : "bg-zinc-100 text-zinc-400",
              )}
            >
              {i < current ? <Check className="size-3" /> : i + 1}
            </span>
            <span className={i <= current ? "text-zinc-800" : "text-zinc-400"}>{s.label}</span>
          </li>
        </Fragment>
      ))}
    </ol>
  );
}

/** Markdown mínimo y seguro (negrita y listas), sin inyectar HTML. */
function RichText({ text }: { text: string }) {
  const inline = (line: string): ReactNode[] =>
    line.split(/(\*\*[^*]+\*\*)/g).map((part, i) => (part.startsWith("**") && part.endsWith("**") ? <strong key={i}>{part.slice(2, -2)}</strong> : part));
  const blocks: ReactNode[] = [];
  let list: ReactNode[] = [];
  const flush = () => {
    if (list.length) blocks.push(<ul key={`l${blocks.length}`} className="my-1 list-disc space-y-0.5 pl-5">{list}</ul>);
    list = [];
  };
  text.split("\n").forEach((raw, i) => {
    const m = raw.match(/^\s*(?:[*-]|\d+\.)\s+(.*)$/);
    if (m) {
      list.push(<li key={i}>{inline(m[1]!)}</li>);
      return;
    }
    flush();
    if (raw.trim()) blocks.push(<p key={i}>{inline(raw)}</p>);
  });
  flush();
  return <div className="space-y-2">{blocks}</div>;
}

export default function Chat() {
  const { user, logout } = useAuth();
  // El cliente ve su propia conversación; el admin llega con /chat/:leadId
  const leadId = Number(useParams().leadId ?? user?.lead_id);
  const qc = useQueryClient();
  const [sending, setSending] = useState(false);
  const [pending, setPending] = useState<string | null>(null);
  const [liveDoc, setLiveDoc] = useState<RequirementDoc | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [text, setText] = useState("");
  const [panel, setPanel] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);

  const state = useQuery({
    queryKey: ["state", leadId],
    queryFn: () => api<LeadState>(`/api/leads/${leadId}/state`),
    refetchInterval: sending ? false : 4000,
  });
  const messages = useQuery({
    queryKey: ["messages", leadId],
    queryFn: () => api<Message[]>(`/api/leads/${leadId}/messages`),
    // Recogemos respuestas asíncronas (estimación terminada, respuesta humana a un escalado)
    refetchInterval: sending ? false : 4000,
  });

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.data, pending]);

  const confirm = useMutation({
    mutationFn: () => post(`/api/leads/${leadId}/requirements/confirm`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["state", leadId] });
      qc.invalidateQueries({ queryKey: ["messages", leadId] });
    },
  });

  async function send() {
    const content = text.trim();
    if (!content || sending) return;
    setText("");
    setPending(content);
    setSending(true);
    setError(null);
    try {
      await streamChat(leadId, content, (event, data) => {
        if (event === "draft") setLiveDoc(data as RequirementDoc);
        if (event === "error") setError((data as { detail: string }).detail);
      });
    } catch (e) {
      setError(e);
    } finally {
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["messages", leadId] }),
        qc.invalidateQueries({ queryKey: ["state", leadId] }),
      ]);
      setPending(null);
      setSending(false);
    }
  }

  const s = state.data;
  const doc = liveDoc ?? s?.draft ?? null;
  const stage = s?.lead.stage;
  const showDoc = !!stage && SHOW_DOC.has(stage) && !!doc;

  const docPanel = showDoc && doc && (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <FileText className="size-4 text-brand-600" /> Requirements document
        </h2>
        {s?.confirmed_version ? <Badge tone="green" dot>v{s.confirmed_version} confirmed</Badge> : <Badge tone="amber" dot>Draft</Badge>}
      </div>
      <RequirementDocView doc={doc} />
      {stage === "requirements" && (
        <div className="rounded-xl bg-zinc-50 p-4 ring-1 ring-zinc-200">
          {s && s.readiness_problems.length > 0 ? (
            <>
              <p className="mb-2 text-xs font-medium text-zinc-700">Still needed before confirming:</p>
              <ul className="mb-3 list-disc space-y-0.5 pl-5 text-xs text-zinc-500">
                {s.readiness_problems.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            </>
          ) : (
            <p className="mb-3 text-xs text-zinc-600">If the summary reflects what you need, confirm it and we'll prepare the estimate.</p>
          )}
          <Button className="w-full" onClick={() => confirm.mutate()} disabled={!s || s.readiness_problems.length > 0} loading={confirm.isPending} icon={<Check />}>
            Confirm agreement
          </Button>
          <ErrorText error={confirm.error} />
        </div>
      )}
      {s && s.proposals.length > 0 && (
        <div className="space-y-2">
          {s.proposals.map((p) => (
            <Button
              key={p.id}
              variant="secondary"
              className="w-full"
              icon={<FileDown />}
              disabled={p.status !== "ready"}
              loading={p.status === "pending"}
              onClick={() => void openProtectedFile(`/api/leads/${leadId}/proposals/${p.id}/pdf`).catch(setError)}
            >
              {p.status === "ready" ? `Download proposal #${p.id}` : p.status === "failed" ? "Could not generate the proposal" : "Generating proposal…"}
            </Button>
          ))}
        </div>
      )}
    </div>
  );

  return (
    <div className="flex h-screen flex-col bg-white">
      <header className="flex h-16 shrink-0 items-center gap-4 border-b border-zinc-100 px-4 sm:px-6">
        {user?.role === "admin" ? (
          <Link to={`/admin/leads/${leadId}`} className="flex items-center gap-1 text-sm font-medium text-zinc-600 hover:text-zinc-900">
            <ChevronLeft className="size-4" /> Internal view
          </Link>
        ) : (
          <Logo />
        )}
        <div className="flex flex-1 justify-center">
          <Stepper stage={stage} />
        </div>
        {showDoc && (
          <Button variant="secondary" size="sm" className="lg:hidden" icon={<FileText />} onClick={() => setPanel(!panel)}>
            Document
          </Button>
        )}
        {user?.role !== "admin" && (
          <Button variant="ghost" size="sm" icon={<LogOut />} onClick={logout}>
            Sign out
          </Button>
        )}
      </header>

      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-0 flex-1 flex-col bg-zinc-50/60">
          <div className="flex-1 overflow-y-auto">
            <div className="mx-auto max-w-3xl space-y-5 px-4 py-8 sm:px-6">
              {messages.data?.map((m) => <Bubble key={m.id} m={m} name={user?.name} />)}
              {pending && (
                <>
                  <Bubble m={{ id: -1, role: "user", agent: null, content: pending, created_at: "" }} name={user?.name} />
                  <div className="flex items-center gap-3">
                    <AssistantAvatar />
                    <div className="flex gap-1 rounded-2xl bg-white px-4 py-3 shadow-card ring-1 ring-zinc-950/5">
                      {[0, 150, 300].map((d) => (
                        <span key={d} className="size-1.5 animate-bounce rounded-full bg-zinc-400" style={{ animationDelay: `${d}ms` }} />
                      ))}
                    </div>
                  </div>
                </>
              )}
              <div ref={bottom} />
            </div>
          </div>
          <div className="border-t border-zinc-100 bg-white px-4 py-4 sm:px-6">
            <form
              className="mx-auto flex max-w-3xl items-end gap-2 rounded-2xl bg-white p-2 shadow-card ring-1 ring-zinc-200 focus-within:ring-2 focus-within:ring-brand-500"
              onSubmit={(e) => {
                e.preventDefault();
                void send();
              }}
            >
              <textarea
                rows={1}
                className="max-h-40 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-sm placeholder:text-zinc-400 focus:outline-none"
                placeholder="Type your message… (Shift + Enter for a new line)"
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void send();
                  }
                }}
                disabled={sending}
              />
              <button
                type="submit"
                disabled={sending || !text.trim()}
                className="grid size-10 shrink-0 place-items-center rounded-xl bg-brand-600 text-white transition hover:bg-brand-700 disabled:bg-zinc-200 disabled:text-zinc-400"
                aria-label="Send"
              >
                <ArrowUp className="size-4" />
              </button>
            </form>
            <div className="mx-auto mt-2 max-w-3xl">
              <ErrorText error={error} />
            </div>
          </div>
        </div>

        {showDoc && <aside className="hidden w-[420px] shrink-0 overflow-y-auto border-l border-zinc-100 p-6 lg:block">{docPanel}</aside>}
        {panel && showDoc && (
          <div className="fixed inset-0 z-40 lg:hidden">
            <div className="absolute inset-0 bg-zinc-950/30" onClick={() => setPanel(false)} />
            <aside className="animate-slide-in absolute inset-y-0 right-0 w-full max-w-md overflow-y-auto bg-white p-6 shadow-pop">{docPanel}</aside>
          </div>
        )}
      </div>
    </div>
  );
}

function AssistantAvatar() {
  return (
    <span className="grid size-8 shrink-0 place-items-center rounded-full bg-brand-50 ring-1 ring-brand-100">
      <HollyMark className="size-6" />
    </span>
  );
}

function Bubble({ m, name }: { m: Message; name?: string }) {
  if (m.role === "user") {
    return (
      <div className="flex justify-end gap-3">
        <div className="max-w-[80%] rounded-2xl rounded-tr-md bg-brand-600 px-4 py-2.5 text-sm whitespace-pre-wrap text-white shadow-sm">{m.content}</div>
        <Avatar name={name} />
      </div>
    );
  }
  const human = m.role === "human";
  return (
    <div className="flex gap-3">
      {human ? <Avatar name="Team" /> : <AssistantAvatar />}
      <div className="max-w-[85%]">
        <div className="mb-1 text-xs font-medium text-zinc-500">{human ? "Team" : "Assistant"}</div>
        <div
          className={cx(
            "rounded-2xl rounded-tl-md px-4 py-3 text-sm leading-relaxed text-zinc-800 shadow-card ring-1",
            human ? "bg-brand-50 ring-brand-200" : "bg-white ring-zinc-950/5",
          )}
        >
          <RichText text={m.content} />
        </div>
      </div>
    </div>
  );
}
