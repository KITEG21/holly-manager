import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FilePlus2, FileText, MessageSquareText, Pencil, ScrollText, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, post, put } from "../../api";
import Markdown, { slugify } from "../../components/Markdown";
import { Badge, Button, cx, Drawer, EmptyState, errorMessage, Input, Segmented, Spinner, useToast } from "../../components/ui";
import { Article, Assistant, type ChatMessage, type Citation, type Doc, type DocDetail } from "./Docs";

const SUGGESTIONS = [
  "What is out of scope for this project?",
  "Which non-functional requirements apply?",
  "What decisions did the client make while we gathered requirements?",
  "What are the main user stories?",
];

const NEW_PAGE = `# Title

## Business rules

-

## Edge cases

-

## Open points

-
`;

/** Documentación del proyecto: el acuerdo de negocio generado, páginas del equipo, archivos y su asistente. */
export default function ProjectDocs({ leadId }: { leadId: number }) {
  const base = `/api/projects/${leadId}/docs`;
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatOpen, setChatOpen] = useState(false);
  const mode = params.get("mode"); // new | edit

  const docs = useQuery({
    queryKey: ["project-docs", leadId],
    queryFn: () => api<Doc[]>(base),
    refetchInterval: (q) => (q.state.data?.some((d) => d.status === "pending") ? 2000 : false),
  });
  const selected = Number(params.get("doc")) || docs.data?.[0]?.id;
  const current = docs.data?.find((d) => d.id === selected);

  const open = (id: number, extra: Record<string, string> = {}) => setParams({ view: "docs", doc: String(id), ...extra });
  const hrefFor = (c: Citation) => {
    const last = c.section?.split(" > ").at(-1);
    return `/dev/projects/${leadId}?view=docs&doc=${c.document_id}${last ? `#${slugify(last)}` : ""}`;
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[220px_minmax(0,1fr)] xl:grid-cols-[220px_minmax(0,1fr)_340px]">
      <aside className="space-y-4">
        <div className="flex flex-wrap gap-2">
          <Button size="sm" icon={<FilePlus2 />} onClick={() => setParams({ view: "docs", mode: "new" })}>
            New page
          </Button>
          <UploadButton leadId={leadId} />
          <Button size="sm" variant="secondary" className="xl:hidden" icon={<MessageSquareText />} onClick={() => setChatOpen(true)}>
            Ask
          </Button>
        </div>
        {docs.isLoading ? (
          <Spinner />
        ) : (
          <nav>
            <ul className="space-y-0.5">
              {docs.data?.map((d) => (
                <li key={d.id}>
                  <button
                    onClick={() => open(d.id)}
                    disabled={d.status === "pending" && !d.title}
                    className={cx(
                      "flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm transition",
                      d.id === selected && mode !== "new" ? "bg-brand-50 font-medium text-brand-700" : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900",
                    )}
                    title={d.error ?? undefined}
                  >
                    {d.source === "agreement" ? <ScrollText className="size-3.5 shrink-0" /> : <FileText className="size-3.5 shrink-0" />}
                    <span className="truncate">{d.title ?? d.filename}</span>
                    {d.status === "pending" && <Badge tone="amber">indexing</Badge>}
                    {d.status === "failed" && <Badge tone="red">failed</Badge>}
                  </button>
                </li>
              ))}
            </ul>
          </nav>
        )}
        <p className="px-1 text-[11px] leading-snug text-zinc-400">
          The business agreement is generated from the requirements the client confirmed. Add pages for the rules, edge cases and decisions the team
          learns along the way.
        </p>
      </aside>

      <main className="min-w-0">
        {mode === "new" ? (
          <PageEditor
            leadId={leadId}
            onDone={(id) => (id ? open(id) : setParams({ view: "docs" }))}
          />
        ) : mode === "edit" && current?.source === "page" ? (
          <PageEditor leadId={leadId} docId={current.id} onDone={() => open(current.id)} />
        ) : current ? (
          <Article
            url={`${base}/${current.id}`}
            actions={
              current.source !== "agreement" && (
                <>
                  {current.source === "page" && (
                    <Button size="sm" variant="secondary" icon={<Pencil />} onClick={() => open(current.id, { mode: "edit" })}>
                      Edit
                    </Button>
                  )}
                  <DeleteButton leadId={leadId} doc={current} onDeleted={() => navigate(`/dev/projects/${leadId}?view=docs`)} />
                </>
              )
            }
          />
        ) : (
          !docs.isLoading && <EmptyState icon={<FileText />} title="No documentation yet" />
        )}
      </main>

      <aside className="hidden xl:block">
        <div className="sticky top-20 h-[calc(100vh-7rem)]">
          <Assistant
            messages={messages}
            setMessages={setMessages}
            askUrl={`${base}/ask`}
            suggestions={SUGGESTIONS}
            hrefFor={hrefFor}
            intro="Answers come only from this project's documentation: the business agreement and the team's pages."
          />
        </div>
      </aside>
      <Drawer open={chatOpen} onClose={() => setChatOpen(false)} title={<span className="text-base font-semibold">Ask this project's docs</span>}>
        <div className="h-[calc(100vh-8rem)]">
          <Assistant
            bare
            messages={messages}
            setMessages={setMessages}
            askUrl={`${base}/ask`}
            suggestions={SUGGESTIONS}
            hrefFor={hrefFor}
            onNavigate={() => setChatOpen(false)}
            intro="Answers come only from this project's documentation: the business agreement and the team's pages."
          />
        </div>
      </Drawer>
    </div>
  );
}

function PageEditor({ leadId, docId, onDone }: { leadId: number; docId?: number; onDone: (id?: number) => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const base = `/api/projects/${leadId}/docs`;
  const existing = useQuery({ queryKey: ["doc", `${base}/${docId}`], queryFn: () => api<DocDetail>(`${base}/${docId}`), enabled: !!docId });
  const [title, setTitle] = useState<string | null>(null);
  const [content, setContent] = useState<string | null>(null);
  const [tab, setTab] = useState<"write" | "preview">("write");

  const t = title ?? existing.data?.title ?? "";
  const c = content ?? existing.data?.content ?? (docId ? "" : NEW_PAGE);

  const save = useMutation({
    mutationFn: () => (docId ? put<DocDetail>(`${base}/${docId}`, { title: t, content: c }) : post<DocDetail>(base, { title: t, content: c })),
    onSuccess: async (d) => {
      toast(d.status === "failed" ? "Saved, but the page could not be indexed for the assistant" : "Page saved", d.status === "failed" ? "error" : "success");
      await Promise.all([qc.invalidateQueries({ queryKey: ["project-docs", leadId] }), qc.invalidateQueries({ queryKey: ["doc", `${base}/${d.id}`] })]);
      onDone(d.id);
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  if (docId && existing.isLoading) return <Spinner />;
  return (
    <section className="rounded-2xl bg-white p-6 shadow-card ring-1 ring-zinc-950/5">
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="min-w-60 flex-1">
          <Input label="Title" placeholder="e.g. Cancellation rules" value={t} onChange={(e) => setTitle(e.target.value)} />
        </div>
        <Segmented
          value={tab}
          onChange={setTab}
          options={[
            { value: "write", label: "Write" },
            { value: "preview", label: "Preview" },
          ]}
        />
      </div>
      {tab === "write" ? (
        <textarea
          className="h-[55vh] w-full resize-y rounded-xl bg-zinc-50 p-4 font-mono text-sm leading-relaxed ring-1 ring-zinc-200 focus:bg-white focus:ring-2 focus:ring-brand-500 focus:outline-none"
          value={c}
          onChange={(e) => setContent(e.target.value)}
          spellCheck
        />
      ) : (
        <div className="min-h-[55vh] rounded-xl p-4 ring-1 ring-zinc-200">
          <Markdown>{c || "*Nothing to preview yet.*"}</Markdown>
        </div>
      )}
      <div className="mt-4 flex items-center justify-between gap-3">
        <p className="text-xs text-zinc-500">Markdown. Use headings (##) so the assistant can cite each section.</p>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => onDone(docId)}>
            Cancel
          </Button>
          <Button loading={save.isPending} disabled={!t.trim() || !c.trim()} onClick={() => save.mutate()}>
            {docId ? "Save changes" : "Create page"}
          </Button>
        </div>
      </div>
    </section>
  );
}

function UploadButton({ leadId }: { leadId: number }) {
  const qc = useQueryClient();
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const upload = useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return api<Doc>(`/api/projects/${leadId}/docs/upload`, { method: "POST", body: fd });
    },
    onSuccess: (d) => {
      toast(`Uploaded ${d.filename}; indexing…`, "success");
      return qc.invalidateQueries({ queryKey: ["project-docs", leadId] });
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });
  return (
    <>
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
      <Button size="sm" variant="secondary" icon={<Upload />} loading={upload.isPending} onClick={() => input.current?.click()}>
        Upload
      </Button>
    </>
  );
}

function DeleteButton({ leadId, doc, onDeleted }: { leadId: number; doc: Doc; onDeleted: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [confirming, setConfirming] = useState(false);
  const remove = useMutation({
    mutationFn: () => api(`/api/projects/${leadId}/docs/${doc.id}`, { method: "DELETE" }),
    onSuccess: async () => {
      toast("Document deleted", "success");
      await qc.invalidateQueries({ queryKey: ["project-docs", leadId] });
      onDeleted();
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });
  return confirming ? (
    <Button size="sm" variant="danger" icon={<Trash2 />} loading={remove.isPending} onClick={() => remove.mutate()} onBlur={() => setConfirming(false)} autoFocus>
      Confirm delete
    </Button>
  ) : (
    <Button size="sm" variant="ghost" icon={<Trash2 />} onClick={() => setConfirming(true)}>
      Delete
    </Button>
  );
}
