import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, BookOpen, FileText, Library, MessageSquareText, RefreshCw, Trash2, Upload, X } from "lucide-react";
import { useEffect, useRef, useState, type Dispatch, type ReactNode, type SetStateAction } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { api, post } from "../../api";
import { useAuth } from "../../auth";
import Markdown, { slugify } from "../../components/Markdown";
import { HollyMark } from "../../components/Shell";
import { Badge, Button, cx, Drawer, EmptyState, errorMessage, Spinner, useToast } from "../../components/ui";

export interface Doc {
  id: number;
  slug: string | null;
  title: string | null;
  filename: string;
  source: "builtin" | "upload" | "agreement" | "page";
  updated_at?: string | null;
  created_at?: string;
  status: "pending" | "ready" | "failed";
  error: string | null;
  chunk_count: number;
}

export interface DocDetail extends Doc {
  content: string | null;
}

export interface Citation {
  id: number;
  document_id: number;
  title: string;
  section: string | null;
  label: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  grounded?: boolean;
}

const SUGGESTIONS = [
  "How is the price of a project calculated?",
  "Why can't I close a task?",
  "What happens when a client asks for a bigger discount?",
  "How does the forecast decide a project is off track?",
];

/** Ruta del documento y ancla de la sección citada (la última parte de "Sección > Subsección"). */
export function citationHref(c: Pick<Citation, "document_id" | "section">) {
  const last = c.section?.split(" > ").at(-1);
  return `/dev/docs/${c.document_id}${last ? `#${slugify(last)}` : ""}`;
}

export default function Docs() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const navigate = useNavigate();
  const params = useParams();
  const [chatOpen, setChatOpen] = useState(false);
  // La conversación vive aquí: sobrevive al cerrar el panel lateral y al navegar entre documentos
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  const docs = useQuery({
    queryKey: ["docs"],
    queryFn: () => api<Doc[]>("/api/docs"),
    refetchInterval: (q) => (q.state.data?.some((d) => d.status === "pending") ? 3000 : false),
  });
  const docId = params.docId ? Number(params.docId) : docs.data?.find((d) => d.status === "ready")?.id;

  const builtin = docs.data?.filter((d) => d.source === "builtin") ?? [];
  const uploaded = docs.data?.filter((d) => d.source === "upload") ?? [];
  const open = (id: number) => navigate(`/dev/docs/${id}`);

  return (
    <div className="grid gap-6 lg:grid-cols-[220px_minmax(0,1fr)] xl:grid-cols-[220px_minmax(0,1fr)_360px]">
      {/* Índice */}
      <aside className="space-y-5 lg:sticky lg:top-20 lg:max-h-[calc(100vh-7rem)] lg:overflow-y-auto">
        <div className="flex items-center justify-between">
          <h1 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
            <Library className="size-5 text-brand-600" /> <span className="text-2xl font-semibold tracking-tight">Documentation</span>
          </h1>
          <Button size="sm" variant="secondary" className="xl:hidden" icon={<MessageSquareText />} onClick={() => setChatOpen(true)}>
            Ask
          </Button>
        </div>
        {docs.isLoading && <Spinner />}
        <DocGroup title="Guides" docs={builtin} current={docId} onOpen={open} />
        {(uploaded.length > 0 || isAdmin) && (
          <DocGroup title="Team documents" docs={uploaded} current={docId} onOpen={open} canDelete={isAdmin} />
        )}
        {isAdmin && <AdminTools />}
      </aside>

      {/* Documento */}
      <main className="min-w-0">
        {docId ? (
          <Article url={`/api/docs/${docId}`} />
        ) : (
          !docs.isLoading && (
            <EmptyState icon={<BookOpen />} title="No documentation yet">
              {isAdmin ? "Sync the built-in guides or upload a document." : "Ask an admin to sync the built-in guides."}
            </EmptyState>
          )
        )}
      </main>

      {/* Asistente */}
      <aside className="hidden xl:block">
        <div className="sticky top-20 h-[calc(100vh-7rem)]">
          <Assistant messages={messages} setMessages={setMessages} />
        </div>
      </aside>
      <Drawer open={chatOpen} onClose={() => setChatOpen(false)} title={<span className="text-base font-semibold">Ask the documentation</span>}>
        <div className="h-[calc(100vh-8rem)]">
          <Assistant bare messages={messages} setMessages={setMessages} onNavigate={() => setChatOpen(false)} />
        </div>
      </Drawer>
    </div>
  );
}

function DocGroup({
  title,
  docs,
  current,
  onOpen,
  canDelete = false,
}: {
  title: string;
  docs: Doc[];
  current?: number;
  onOpen: (id: number) => void;
  canDelete?: boolean;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const [confirming, setConfirming] = useState<number | null>(null);
  const remove = useMutation({
    mutationFn: (id: number) => api(`/api/docs/${id}`, { method: "DELETE" }),
    onSuccess: (_, id) => {
      toast("Document deleted", "success");
      if (id === current) navigate("/dev/docs");
      return qc.invalidateQueries({ queryKey: ["docs"] });
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  return (
    <nav>
      <p className="mb-1.5 px-2 text-[11px] font-medium tracking-wider text-zinc-500 uppercase">{title}</p>
      {docs.length === 0 && <p className="px-2 text-xs text-zinc-400">None yet.</p>}
      <ul className="space-y-0.5">
        {docs.map((d) => (
          <li key={d.id} className="group flex items-center gap-1">
            <button
              disabled={d.status !== "ready"}
              onClick={() => onOpen(d.id)}
              className={cx(
                "flex min-w-0 flex-1 items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm transition",
                d.id === current ? "bg-brand-50 font-medium text-brand-700" : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900",
                d.status !== "ready" && "cursor-default opacity-70",
              )}
              title={d.error ?? undefined}
            >
              <FileText className="size-3.5 shrink-0" />
              <span className="truncate">{d.title ?? d.filename}</span>
              {d.status === "pending" && <Badge tone="amber">indexing</Badge>}
              {d.status === "failed" && <Badge tone="red">failed</Badge>}
            </button>
            {canDelete &&
              (confirming === d.id ? (
                <button
                  onClick={() => remove.mutate(d.id)}
                  onBlur={() => setConfirming(null)}
                  autoFocus
                  className="rounded-md bg-rose-600 px-1.5 py-0.5 text-[11px] font-medium text-white"
                >
                  Delete
                </button>
              ) : (
                <button
                  onClick={() => setConfirming(d.id)}
                  className="rounded p-1 text-zinc-300 opacity-0 transition group-hover:opacity-100 hover:text-rose-600 focus:opacity-100"
                  aria-label={`Delete ${d.title ?? d.filename}`}
                >
                  <Trash2 className="size-3.5" />
                </button>
              ))}
          </li>
        ))}
      </ul>
    </nav>
  );
}

function AdminTools() {
  const qc = useQueryClient();
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const upload = useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return api<Doc>("/api/docs", { method: "POST", body: fd });
    },
    onSuccess: (d) => {
      toast(`Uploaded ${d.filename}; indexing…`, "success");
      return qc.invalidateQueries({ queryKey: ["docs"] });
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });
  const sync = useMutation({
    mutationFn: () => post("/api/docs/sync"),
    onSuccess: () => {
      toast("Syncing the built-in guides…");
      setTimeout(() => qc.invalidateQueries({ queryKey: ["docs"] }), 4000);
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });
  return (
    <div className="space-y-2 border-t border-zinc-200 pt-4">
      <input
        ref={input}
        type="file"
        accept=".md,.markdown,.txt,.pdf,.docx,.html,.pptx"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) upload.mutate(f);
          e.target.value = "";
        }}
      />
      <Button size="sm" variant="secondary" className="w-full" icon={<Upload />} loading={upload.isPending} onClick={() => input.current?.click()}>
        Upload document
      </Button>
      <Button size="sm" variant="ghost" className="w-full" icon={<RefreshCw />} loading={sync.isPending} onClick={() => sync.mutate()}>
        Resync built-in guides
      </Button>
      <p className="px-1 text-[11px] leading-snug text-zinc-400">Markdown, PDF, DOCX, HTML or PPTX. Built-in guides live in backend/docs.</p>
    </div>
  );
}

const SOURCE_BADGE: Record<Doc["source"], { label: string; tone: "indigo" | "slate" | "green" | "blue" }> = {
  builtin: { label: "Guide", tone: "indigo" },
  upload: { label: "Uploaded file", tone: "slate" },
  agreement: { label: "Generated from the agreement", tone: "green" },
  page: { label: "Team page", tone: "blue" },
};

/** Documento renderizado; lleva a la sección citada (hash de la URL) y la resalta. */
export function Article({ url, actions }: { url: string; actions?: ReactNode }) {
  const location = useLocation();
  const doc = useQuery({ queryKey: ["doc", url], queryFn: () => api<DocDetail>(url) });

  // Lleva a la sección citada y la resalta un momento
  useEffect(() => {
    if (!doc.data?.content) return;
    const id = decodeURIComponent(location.hash.slice(1));
    if (!id) {
      window.scrollTo({ top: 0 });
      return;
    }
    const el = document.getElementById(id);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    el.classList.add("bg-brand-50", "rounded-md", "transition-colors");
    const t = setTimeout(() => el.classList.remove("bg-brand-50"), 2000);
    return () => clearTimeout(t);
  }, [doc.data?.content, location.hash]);

  if (doc.isLoading) return <Spinner />;
  if (!doc.data?.content) return <EmptyState icon={<FileText />} title="This document has no content yet" />;
  return (
    <article className="rounded-2xl bg-white px-6 py-8 shadow-card ring-1 ring-zinc-950/5 sm:px-10">
      <div className="mb-6 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
        <Badge tone={SOURCE_BADGE[doc.data.source].tone}>{SOURCE_BADGE[doc.data.source].label}</Badge>
        <span>{doc.data.chunk_count} indexed sections</span>
        {doc.data.updated_at && <span>· updated {new Date(doc.data.updated_at).toLocaleDateString("en-US", { day: "numeric", month: "short" })}</span>}
        {actions && <div className="ml-auto flex gap-2">{actions}</div>}
      </div>
      <Markdown>{doc.data.content}</Markdown>
    </article>
  );
}

export function Assistant({
  bare = false,
  messages,
  setMessages,
  onNavigate,
  askUrl = "/api/docs/ask",
  suggestions = SUGGESTIONS,
  hrefFor = citationHref,
  intro = "Answers come only from the documentation, with links to the sections they are based on.",
}: {
  bare?: boolean;
  messages: ChatMessage[];
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>;
  onNavigate?: () => void;
  askUrl?: string;
  suggestions?: string[];
  hrefFor?: (c: Citation) => string;
  intro?: string;
}) {
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const bottom = useRef<HTMLDivElement>(null);
  const ask = useMutation({
    mutationFn: (question: string) =>
      post<{ answer: string; grounded: boolean; citations: Citation[] }>(askUrl, {
        question,
        // Las marcas [Cn] de respuestas anteriores no significan nada para la nueva búsqueda
        history: messages.slice(-10).map((m) => ({ role: m.role, content: m.content.replace(/\[C\d+\]/g, "") })),
      }),
    onSuccess: (r) => setMessages((m) => [...m, { role: "assistant", content: r.answer, citations: r.citations, grounded: r.grounded }]),
    onError: (e) => setMessages((m) => [...m, { role: "assistant", content: errorMessage(e), grounded: false, citations: [] }]),
  });

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, ask.isPending]);

  function send(q: string) {
    const question = q.trim();
    if (!question || ask.isPending) return;
    setMessages((m) => [...m, { role: "user", content: question }]);
    setText("");
    ask.mutate(question);
  }

  const go = (c: Citation) => {
    navigate(hrefFor(c));
    onNavigate?.();
  };

  return (
    <section className={cx("flex h-full flex-col", !bare && "rounded-2xl bg-white shadow-card ring-1 ring-zinc-950/5")}>
      {!bare && (
        <header className="flex items-center justify-between border-b border-zinc-100 px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <HollyMark className="size-7" />
            <span className="text-[15px] font-semibold tracking-tight">Ask the documentation</span>
          </div>
          {messages.length > 0 && (
            <button onClick={() => setMessages([])} className="rounded p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700" title="Clear conversation" aria-label="Clear conversation">
              <X className="size-4" />
            </button>
          )}
        </header>
      )}

      <div className={cx("flex-1 space-y-4 overflow-y-auto", bare ? "py-2" : "p-4")}>
        {messages.length === 0 && (
          <div className="space-y-3">
            <p className="text-sm text-zinc-500">{intro}</p>
            <div className="space-y-2">
              {suggestions.map((s) => (
                <button key={s} onClick={() => send(s)} className="w-full rounded-xl px-3 py-2 text-left text-sm text-zinc-700 ring-1 ring-zinc-200 transition hover:bg-brand-50 hover:ring-brand-200">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="flex justify-end">
              <div className="max-w-[85%] rounded-2xl rounded-tr-md bg-brand-600 px-3.5 py-2 text-sm text-white">{m.content}</div>
            </div>
          ) : (
            <div key={i} className="space-y-2">
              <div className={cx("rounded-2xl rounded-tl-md px-3.5 py-2.5 text-sm", m.grounded ? "bg-zinc-50 ring-1 ring-zinc-200" : "bg-amber-50 ring-1 ring-amber-200")}>
                <Markdown
                  className="prose-sm prose-p:my-1.5 prose-ul:my-1.5 prose-li:my-0.5"
                  onCite={(id) => {
                    const c = m.citations?.find((x) => x.id === id);
                    if (c) go(c);
                  }}
                >
                  {m.content}
                </Markdown>
              </div>
              {!!m.citations?.length && (
                <div className="flex flex-wrap gap-1.5">
                  {m.citations.map((c) => (
                    <button
                      key={c.id}
                      onClick={() => go(c)}
                      className="inline-flex max-w-full items-center gap-1 rounded-md bg-white px-2 py-1 text-left text-[11px] text-zinc-600 ring-1 ring-zinc-200 hover:text-brand-700 hover:ring-brand-200"
                      title={c.label}
                    >
                      {m.grounded && <span className="font-semibold text-brand-700">{c.id}</span>}
                      <span className="truncate">
                        {c.title}
                        {c.section && ` › ${c.section.split(" > ").at(-1)}`}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ),
        )}
        {ask.isPending && (
          <div className="flex w-16 gap-1 rounded-2xl bg-zinc-50 px-3.5 py-3 ring-1 ring-zinc-200">
            {[0, 150, 300].map((d) => (
              <span key={d} className="size-1.5 animate-bounce rounded-full bg-zinc-400" style={{ animationDelay: `${d}ms` }} />
            ))}
          </div>
        )}
        <div ref={bottom} />
      </div>

      <form
        className={cx("flex items-end gap-2 border-t border-zinc-100", bare ? "pt-3" : "p-3")}
        onSubmit={(e) => {
          e.preventDefault();
          send(text);
        }}
      >
        <textarea
          rows={1}
          className="max-h-32 min-h-9 flex-1 resize-none rounded-xl bg-zinc-50 px-3 py-2 text-sm ring-1 ring-zinc-200 placeholder:text-zinc-400 focus:bg-white focus:ring-2 focus:ring-brand-500 focus:outline-none"
          placeholder="Ask a question…"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(text);
            }
          }}
        />
        <button
          type="submit"
          disabled={ask.isPending || !text.trim()}
          className="grid size-9 shrink-0 place-items-center rounded-xl bg-brand-600 text-white transition hover:bg-brand-700 disabled:bg-zinc-200 disabled:text-zinc-400"
          aria-label="Send"
        >
          <ArrowUp className="size-4" />
        </button>
      </form>
    </section>
  );
}
