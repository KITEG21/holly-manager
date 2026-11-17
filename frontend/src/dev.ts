import { useMutation, useQueryClient } from "@tanstack/react-query";
import { patch, post, api } from "./api";
import type { Tone } from "./components/ui";

export type Status = "todo" | "in_progress" | "done";

export interface Forecast {
  committed_hours: number;
  logged_hours: number;
  remaining_hours: number;
  forecast_hours: number;
  performance_ratio: number;
  deviation_pct: number;
  done_tasks: number;
  total_tasks: number;
  remaining_sprints: number;
  alert: boolean;
  alert_message: string | null;
}

export interface Task {
  id: number;
  key: string;
  lead_id: number;
  project: string;
  story_id: string;
  story: string;
  title: string;
  task_type: string;
  depends_on: string[];
  sprint: number;
  planned_hours: number;
  actual_hours: number;
  status: Status;
  blocked_by: string[];
  assignee_id: number | null;
  assignee: string | null;
  done_at: string | null;
}

export interface ProjectSummary {
  lead_id: number;
  name: string;
  forecast: Forecast;
}

export interface ProjectDetail extends ProjectSummary {
  sprint_weeks: number;
  sprints: { number: number; planned_hours: number; actual_hours: number; tasks: Task[] }[];
}

export interface TimeEntry {
  id: number;
  task_id: number;
  hours: number;
  note: string | null;
  user_id: number;
  user: string;
  work_date: string;
  created_at: string;
}

export interface Member {
  id: number;
  name: string;
  role: "developer" | "admin";
}

export interface Activity {
  user: string;
  hours: number;
  work_date: string;
  note: string | null;
  task_id: number;
  key: string;
  title: string;
  project: string;
  lead_id: number;
}

export interface Dashboard {
  today_hours: number;
  week_hours: number;
  week_target_hours: number;
  my_open_tasks: number;
  my_in_progress: number;
  team_done_this_week: number;
  projects: ProjectSummary[];
  my_tasks: Task[];
  activity: Activity[];
}

export interface Timesheet {
  week_start: string;
  days: string[];
  rows: { task_id: number; key: string; title: string; project: string; status: Status; hours: number[]; total: number }[];
  day_totals: number[];
  total: number;
  entries: TimeEntry[];
}

export interface Reports {
  projects: ProjectSummary[];
  accuracy_by_type: { task_type: string; tasks: number; planned_hours: number; actual_hours: number; ratio: number }[];
  weekly_hours: { week_start: string; user: string; hours: number }[];
  weeks: string[];
}

export const STATUS_LABEL: Record<Status, string> = { todo: "To do", in_progress: "In progress", done: "Done" };
export const STATUS_TONE: Record<Status, Tone> = { todo: "slate", in_progress: "blue", done: "green" };
export const STATUSES: Status[] = ["todo", "in_progress", "done"];

export const TYPE_LABEL: Record<string, string> = {
  backend: "Backend",
  frontend: "Frontend",
  integration: "Integration",
  qa: "QA",
  devops: "DevOps",
  design: "Design",
};

// Hasta dos decimales y sin ceros sobrantes: 0.25 h, 1.5 h, 3 h
export const hours = (h: number) => `${Number(h.toFixed(2))} h`;

/** Fecha local en formato ISO (yyyy-mm-dd), sin el desfase de toISOString. */
export function isoDate(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function parseDate(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y!, m! - 1, d!);
}

/** Invalida todo lo que depende de las tareas y las horas, para que cada vista se refresque. */
export function useRefreshWork() {
  const qc = useQueryClient();
  return () =>
    Promise.all(
      ["dev-projects", "dev-project", "dev-tasks", "dashboard", "timesheet", "reports", "time"].map((k) =>
        qc.invalidateQueries({ queryKey: [k] }),
      ),
    );
}

export function useTaskActions() {
  const refresh = useRefreshWork();
  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: number; status: Status }) => patch(`/api/dev/tasks/${id}`, { status }),
    onSuccess: refresh,
  });
  const assign = useMutation({
    mutationFn: ({ id, userId }: { id: number; userId: number | null }) =>
      post(`/api/dev/tasks/${id}/assign`, { user_id: userId }),
    onSuccess: refresh,
  });
  const logTime = useMutation({
    mutationFn: ({ id, hours, note, workDate }: { id: number; hours: number; note?: string; workDate?: string }) =>
      post(`/api/dev/tasks/${id}/time`, { hours, note: note || null, work_date: workDate ?? null }),
    onSuccess: refresh,
  });
  const deleteTime = useMutation({
    mutationFn: (entryId: number) => api(`/api/dev/time/${entryId}`, { method: "DELETE" }),
    onSuccess: refresh,
  });
  return { setStatus, assign, logTime, deleteTime };
}
