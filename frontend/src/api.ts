export type Stage =
  | "qualification"
  | "requirements"
  | "estimating"
  | "commercial"
  | "closed"
  | "nurture"
  | "discarded";

export interface Lead {
  id: number;
  name: string;
  email: string | null;
  stage: Stage;
  qualification_status: string;
  qualification_score: number | null;
  created_at: string;
}

export interface Message {
  id: number;
  role: "user" | "assistant" | "human";
  agent: string | null;
  content: string;
  created_at: string;
  meta?: {
    trace_id?: string;
    tool_calls?: { name: string; args: Record<string, unknown> }[];
    rules?: string[];
    violations?: { code: string; message: string; requested?: string; limit?: string }[];
    citations?: { id: number; label: string; similarity: number }[];
  };
}

export interface UserStory {
  id: string;
  epic_id: string;
  as_a: string;
  i_want: string;
  so_that: string;
  acceptance_criteria: string[];
  source_message_ids: number[];
}

export interface RequirementDoc {
  epics: { id: string; title: string; description: string }[];
  stories: UserStory[];
  nfrs: { id: string; category: string; text: string }[];
  out_of_scope: string[];
  ambiguities: { id: string; question: string; status: "open" | "resolved"; resolution: string | null }[];
  summary: string | null;
}

export interface LeadState {
  lead: Lead;
  draft: RequirementDoc | null;
  readiness_problems: string[];
  confirmed_version: number | null;
  proposals: { id: number; status: string }[];
}

export interface TaskEstimate {
  task: { id: string; story_id: string; title: string; task_type: string; depends_on: string[] };
  optimistic: number;
  likely: number;
  pessimistic: number;
  expected: number;
  std_dev: number;
  planned_hours: number;
  historical_refs: { project: string; title: string; actual_hours: number; similarity: number }[];
  basis: string;
}

export interface EstimateResult {
  tasks: TaskEstimate[];
  sprints: { number: number; task_ids: string[]; planned_hours: number; capacity_hours: number }[];
  totals: {
    expected_hours: number;
    std_dev_hours: number;
    p80_hours: number;
    risk_margin_pct: number;
    committed_hours: number;
  };
  quote: {
    currency: string;
    hourly_rate: string;
    hours: number;
    list_price: string;
    min_price_applied: boolean;
    price: string;
    payments: { name: string; pct: string; amount: string }[];
  };
  weeks: number;
  scope_exceeds_max: boolean;
  warnings: string[];
}

export interface Escalation {
  id: number;
  lead_id: number;
  lead_name: string;
  reason: string;
  client_request: string;
  summary: string;
  violations: { code: string; message: string; requested?: string; limit?: string }[];
  status: "open" | "resolved";
  resolution: string | null;
  created_at: string;
}

/** Mensaje legible para los errores de FastAPI/Pydantic (string, lista de errores o {problems}). */
function describe(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).filter((x) => x !== "body").join(".")}: ${d.msg}`)
      .join("; ");
  }
  if (detail && typeof detail === "object" && "problems" in detail) {
    return (detail as { problems: string[] }).problems.join(" ");
  }
  return JSON.stringify(detail);
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
  ) {
    super(describe(detail));
  }
}

// --- Sesión ------------------------------------------------------------------------------------

export type Role = "client" | "developer" | "admin";

export interface User {
  id: number;
  email: string;
  name: string;
  role: Role;
  lead_id: number | null;
}

const TOKEN_KEY = "holly.token";
let token: string | null = null;
try {
  token = localStorage.getItem(TOKEN_KEY);
} catch {
  token = null;
}

export function setToken(value: string | null) {
  token = value;
  try {
    if (value) localStorage.setItem(TOKEN_KEY, value);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // sin almacenamiento la sesión dura lo que la pestaña
  }
}

export const hasToken = () => token !== null;

/** Se dispara cuando el servidor rechaza el token: la app vuelve al login. */
export const onUnauthorized = new EventTarget();

function authHeaders(extra?: HeadersInit): Record<string, string> {
  const headers: Record<string, string> = { ...(extra as Record<string, string>) };
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

async function authFetch(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(path, { ...init, headers: authHeaders(init?.headers) });
  if (res.status === 401 && token) {
    setToken(null);
    onUnauthorized.dispatchEvent(new Event("unauthorized"));
  }
  return res;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await authFetch(path, {
    ...init,
    headers: init?.body instanceof FormData ? init.headers : { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? body);
  }
  return res.json() as Promise<T>;
}

export const put = <T>(path: string, body: unknown) => api<T>(path, { method: "PUT", body: JSON.stringify(body) });
export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
export const patch = <T>(path: string, body: unknown) =>
  api<T>(path, { method: "PATCH", body: JSON.stringify(body) });

/** Descarga un fichero protegido (un <a href> no puede enviar la cabecera Authorization). */
export async function openProtectedFile(path: string): Promise<void> {
  const res = await authFetch(path);
  if (!res.ok) throw new ApiError(res.status, await res.text());
  const url = URL.createObjectURL(await res.blob());
  window.open(url, "_blank");
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/** SSE sobre POST: EventSource solo admite GET, así que leemos el stream a mano. */
export async function streamChat(
  leadId: number,
  content: string,
  onEvent: (event: string, data: unknown) => void,
): Promise<void> {
  const res = await authFetch(`/api/leads/${leadId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!res.ok || !res.body) throw new ApiError(res.status, await res.text());
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value.replace(/\r\n/g, "\n");
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      let event = "message";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
      }
      if (data.length) onEvent(event, JSON.parse(data.join("\n")));
    }
  }
}

export const STAGE_LABEL: Record<Stage, string> = {
  qualification: "Qualification",
  requirements: "Requirements",
  estimating: "Estimating",
  commercial: "Proposal",
  closed: "Closed",
  nurture: "Nurture",
  discarded: "Discarded",
};

export const JAEGER_URL = import.meta.env.VITE_JAEGER_URL ?? "http://localhost:16687";

export function formatMoney(value: string | number, currency = "EUR"): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(Number(value));
}
