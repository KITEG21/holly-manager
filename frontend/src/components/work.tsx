/** Piezas compartidas de la zona de equipo: cronómetro global, panel de detalle de tarea y tarjetas. */
import { useQuery } from "@tanstack/react-query";
import { CalendarDays, Clock, GitBranch, Lock, Pause, Play, Trash2, UserRound } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import {
  hours,
  isoDate,
  parseDate,
  STATUS_LABEL,
  STATUS_TONE,
  STATUSES,
  TYPE_LABEL,
  useTaskActions,
  type Member,
  type Status,
  type Task,
  type TimeEntry,
} from "../dev";
import { Avatar, Badge, Button, cx, Drawer, errorMessage, Input, Progress, Select, Spinner, useToast } from "./ui";

// --- Cronómetro ----------------------------------------------------------------------------------

interface RunningTimer {
  taskId: number;
  label: string;
  startedAt: number;
}

interface TimerState {
  running: RunningTimer | null;
  start: (task: Task) => void;
  stop: () => Promise<void>;
}

const TimerContext = createContext<TimerState | null>(null);
const TIMER_KEY = "holly.timer";

function readTimer(): RunningTimer | null {
  try {
    const raw = localStorage.getItem(TIMER_KEY);
    return raw ? (JSON.parse(raw) as RunningTimer) : null;
  } catch {
    return null;
  }
}

function writeTimer(t: RunningTimer | null) {
  try {
    if (t) localStorage.setItem(TIMER_KEY, JSON.stringify(t));
    else localStorage.removeItem(TIMER_KEY);
  } catch {
    // sin almacenamiento el cronómetro vive solo en esta pestaña
  }
}

/** Redondea a cuartos de hora, con un mínimo de 15 minutos. */
export const roundQuarter = (ms: number) => Math.max(0.25, Math.round(ms / 900_000) / 4);

export function TimerProvider({ children }: { children: ReactNode }) {
  const [running, setRunning] = useState<RunningTimer | null>(readTimer);
  const { logTime } = useTaskActions();
  const toast = useToast();

  const start = useCallback(
    (task: Task) => {
      const t = { taskId: task.id, label: `${task.key} · ${task.title}`, startedAt: Date.now() };
      writeTimer(t);
      setRunning(t);
      toast(`Timer running: ${task.key}`);
    },
    [toast],
  );

  const stop = useCallback(async () => {
    if (!running) return;
    const h = roundQuarter(Date.now() - running.startedAt);
    try {
      await logTime.mutateAsync({ id: running.taskId, hours: h, note: "Timer" });
      toast(`Logged ${hours(h)} to ${running.label.split(" · ")[0]}`, "success");
      writeTimer(null);
      setRunning(null);
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  }, [running, logTime, toast]);

  return <TimerContext.Provider value={{ running, start, stop }}>{children}</TimerContext.Provider>;
}

export function useTimer(): TimerState {
  const ctx = useContext(TimerContext);
  if (!ctx) throw new Error("useTimer used outside TimerProvider");
  return ctx;
}

function useElapsed(since: number | undefined) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!since) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [since]);
  if (!since) return "00:00:00";
  const s = Math.max(0, Math.floor((now - since) / 1000));
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(Math.floor(s / 3600))}:${p(Math.floor((s % 3600) / 60))}:${p(s % 60)}`;
}

export function TimerWidget() {
  const { running, stop } = useTimer();
  const { openTask } = useTaskDrawer();
  const elapsed = useElapsed(running?.startedAt);
  const [stopping, setStopping] = useState(false);
  if (!running) {
    return (
      <span className="hidden items-center gap-1.5 text-xs text-zinc-400 sm:flex">
        <Clock className="size-3.5" /> No timer running
      </span>
    );
  }
  return (
    <div className="flex items-center gap-2 rounded-full bg-brand-50 py-1 pr-1 pl-3 ring-1 ring-brand-200">
      <span className="relative flex size-2">
        <span className="absolute inline-flex size-full animate-ping rounded-full bg-brand-500 opacity-60" />
        <span className="relative inline-flex size-2 rounded-full bg-brand-600" />
      </span>
      <button onClick={() => openTask(running.taskId)} className="max-w-48 truncate text-xs font-medium text-brand-700 hover:underline">
        {running.label}
      </button>
      <span className="font-mono text-xs text-brand-700 tabular-nums">{elapsed}</span>
      <button
        onClick={async () => {
          setStopping(true);
          await stop();
          setStopping(false);
        }}
        disabled={stopping}
        className="grid size-7 place-items-center rounded-full bg-brand-600 text-white hover:bg-brand-700"
        aria-label="Stop and log"
        title="Stop and log"
      >
        <Pause className="size-3.5" />
      </button>
    </div>
  );
}

// --- Panel de detalle de tarea -------------------------------------------------------------------

const DrawerContext = createContext<{ openTask: (id: number) => void }>({ openTask: () => {} });
export const useTaskDrawer = () => useContext(DrawerContext);

export function TaskDrawerProvider({ children }: { children: ReactNode }) {
  const [taskId, setTaskId] = useState<number | null>(null);
  const close = useCallback(() => setTaskId(null), []);
  return (
    <DrawerContext.Provider value={{ openTask: setTaskId }}>
      {children}
      {taskId != null && <TaskDrawer taskId={taskId} onClose={close} />}
    </DrawerContext.Provider>
  );
}

function TaskDrawer({ taskId, onClose }: { taskId: number; onClose: () => void }) {
  const { user } = useAuth();
  const toast = useToast();
  const timer = useTimer();
  const tasks = useQuery({ queryKey: ["dev-tasks", "all"], queryFn: () => api<Task[]>("/api/dev/tasks") });
  const team = useQuery({ queryKey: ["team"], queryFn: () => api<Member[]>("/api/dev/team"), staleTime: 60_000 });
  const entries = useQuery({ queryKey: ["time", taskId], queryFn: () => api<TimeEntry[]>(`/api/dev/tasks/${taskId}/time`) });
  const { setStatus, assign, logTime, deleteTime } = useTaskActions();
  const [h, setH] = useState("");
  const [note, setNote] = useState("");
  const [day, setDay] = useState(isoDate(new Date()));

  const t = tasks.data?.find((x) => x.id === taskId);
  const run = (p: Promise<unknown>, ok?: string) =>
    p.then(() => ok && toast(ok, "success")).catch((e) => toast(errorMessage(e), "error"));

  return (
    <Drawer
      open
      onClose={onClose}
      title={
        t ? (
          <div>
            <div className="flex items-center gap-2 text-xs text-zinc-500">
              <span className="font-mono font-medium text-brand-700">{t.key}</span>
              <span>·</span>
              <span className="truncate">{t.project}</span>
              <span>·</span>
              <span>Sprint {t.sprint}</span>
            </div>
            <h2 className="mt-1 text-base font-semibold text-zinc-900">{t.title}</h2>
          </div>
        ) : (
          <span className="text-sm text-zinc-500">Task</span>
        )
      }
    >
      {!t ? (
        <Spinner />
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-3">
            <Select
              label="Status"
              value={t.status}
              disabled={setStatus.isPending}
              onChange={(e) => run(setStatus.mutateAsync({ id: t.id, status: e.target.value as Status }), "Status updated")}
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {STATUS_LABEL[s]}
                </option>
              ))}
            </Select>
            <Select
              label="Assignee"
              value={t.assignee_id ?? ""}
              disabled={assign.isPending}
              onChange={(e) =>
                run(assign.mutateAsync({ id: t.id, userId: e.target.value ? Number(e.target.value) : null }), "Assignee updated")
              }
            >
              <option value="">Unassigned</option>
              {team.data?.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </Select>
          </div>

          <div className="rounded-xl bg-zinc-50 p-4">
            <div className="flex items-baseline justify-between">
              <span className="text-xs font-medium text-zinc-500">Actual / planned hours</span>
              <span className={cx("text-sm font-semibold tabular-nums", t.actual_hours > t.planned_hours && "text-rose-600")}>
                {hours(t.actual_hours)} / {hours(t.planned_hours)}
              </span>
            </div>
            <Progress className="mt-2" value={t.actual_hours} max={t.planned_hours} tone={t.actual_hours > t.planned_hours ? "danger" : "brand"} />
          </div>

          <dl className="space-y-3 text-sm">
            <Meta icon={<UserRound />} label="Agreed story">
              <span className="font-mono text-xs text-zinc-500">{t.story_id}</span> {t.story}
            </Meta>
            <Meta icon={<GitBranch />} label="Type">
              {TYPE_LABEL[t.task_type] ?? t.task_type}
            </Meta>
            {t.depends_on.length > 0 && (
              <Meta icon={<Lock />} label="Depends on">
                {t.depends_on.map((d) => (
                  <Badge key={d} tone={t.blocked_by.includes(d) ? "amber" : "green"} dot>
                    {d}
                  </Badge>
                ))}
              </Meta>
            )}
          </dl>

          <section>
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold">Log time</h3>
              {timer.running?.taskId === t.id ? (
                <Badge tone="indigo" dot>
                  Timer running
                </Badge>
              ) : (
                <Button
                  size="sm"
                  variant="secondary"
                  icon={<Play />}
                  disabled={t.status === "done" || t.blocked_by.length > 0}
                  onClick={() => timer.start(t)}
                >
                  Start timer
                </Button>
              )}
            </div>
            <form
              className="grid grid-cols-[90px_1fr] gap-2 sm:grid-cols-[90px_140px_1fr_auto]"
              onSubmit={(e) => {
                e.preventDefault();
                run(
                  logTime.mutateAsync({ id: t.id, hours: Number(h), note, workDate: day }).then(() => {
                    setH("");
                    setNote("");
                  }),
                  "Time logged",
                );
              }}
            >
              <Input type="number" step="0.25" min="0.25" max="24" placeholder="Hours" value={h} onChange={(e) => setH(e.target.value)} required />
              <Input type="date" value={day} max={isoDate(new Date())} onChange={(e) => setDay(e.target.value)} required />
              <Input className="col-span-2 sm:col-span-1" placeholder="What did you do? (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
              <Button type="submit" loading={logTime.isPending} disabled={!h} className="col-span-2 sm:col-span-1">
                Log
              </Button>
            </form>
            {t.blocked_by.length > 0 && t.status === "todo" && (
              <p className="mt-2 text-xs text-amber-700">Blocked until {t.blocked_by.join(", ")} is done.</p>
            )}
          </section>

          <section>
            <h3 className="mb-2 text-sm font-semibold">History</h3>
            {entries.data?.length === 0 && <p className="text-sm text-zinc-500">No time logged yet.</p>}
            <ul className="divide-y divide-zinc-100">
              {entries.data?.map((e) => (
                <li key={e.id} className="group flex items-center gap-3 py-2.5 text-sm">
                  <Avatar name={e.user} size="sm" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-zinc-800">{e.note || <span className="text-zinc-400">No note</span>}</div>
                    <div className="flex items-center gap-1 text-xs text-zinc-500">
                      <CalendarDays className="size-3" />
                      {parseDate(e.work_date).toLocaleDateString("en-US", { weekday: "short", day: "numeric", month: "short" })} · {e.user}
                    </div>
                  </div>
                  <span className="font-medium tabular-nums">{hours(e.hours)}</span>
                  {(e.user_id === user?.id || user?.role === "admin") && (
                    <button
                      className="rounded p-1 text-zinc-300 opacity-0 transition group-hover:opacity-100 hover:bg-rose-50 hover:text-rose-600 focus:opacity-100"
                      aria-label="Delete time entry"
                      onClick={() => run(deleteTime.mutateAsync(e.id), "Time entry deleted")}
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </Drawer>
  );
}

function Meta({ icon, label, children }: { icon: ReactNode; label: string; children: ReactNode }) {
  return (
    <div className="flex gap-3">
      <dt className="flex w-36 shrink-0 items-center gap-2 text-xs text-zinc-500 [&>svg]:size-3.5">
        {icon}
        {label}
      </dt>
      <dd className="flex min-w-0 flex-wrap items-center gap-1 text-zinc-800">{children}</dd>
    </div>
  );
}

// --- Tarjeta y fila de tarea ---------------------------------------------------------------------

export function TaskCard({ task: t, draggable = false }: { task: Task; draggable?: boolean }) {
  const { openTask } = useTaskDrawer();
  const over = t.actual_hours > t.planned_hours;
  return (
    <button
      draggable={draggable}
      onDragStart={(e) => {
        e.dataTransfer.setData("text/task", String(t.id));
        e.dataTransfer.effectAllowed = "move";
      }}
      onClick={() => openTask(t.id)}
      className="group w-full rounded-xl bg-white p-3 text-left shadow-card ring-1 ring-zinc-950/5 transition hover:shadow-pop hover:ring-brand-200"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-[11px] font-medium text-brand-700">{t.key}</span>
        <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] font-medium text-zinc-600 uppercase">
          {TYPE_LABEL[t.task_type] ?? t.task_type}
        </span>
      </div>
      <p className="mt-1.5 line-clamp-2 text-sm font-medium text-zinc-800">{t.title}</p>
      {t.blocked_by.length > 0 && t.status !== "done" && (
        <p className="mt-1.5 flex items-center gap-1 text-xs text-amber-700">
          <Lock className="size-3" /> Waiting on {t.blocked_by.join(", ")}
        </p>
      )}
      <div className="mt-3 flex items-center justify-between gap-2">
        {t.assignee ? <Avatar name={t.assignee} size="sm" /> : <span className="size-6 rounded-full border border-dashed border-zinc-300" title="Unassigned" />}
        <span className={cx("text-xs tabular-nums", over ? "font-medium text-rose-600" : "text-zinc-500")}>
          {hours(t.actual_hours)} / {hours(t.planned_hours)}
        </span>
      </div>
      <Progress className="mt-2" value={t.actual_hours} max={t.planned_hours} tone={over ? "danger" : t.status === "done" ? "success" : "brand"} />
    </button>
  );
}

export function TaskRow({ task: t, showProject = false }: { task: Task; showProject?: boolean }) {
  const { openTask } = useTaskDrawer();
  const over = t.actual_hours > t.planned_hours;
  return (
    <button onClick={() => openTask(t.id)} className="flex w-full items-center gap-4 px-5 py-3 text-left transition hover:bg-zinc-50">
      <span className="w-10 shrink-0 font-mono text-xs font-medium text-brand-700">{t.key}</span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-zinc-800">{t.title}</p>
        <p className="truncate text-xs text-zinc-500">
          {showProject && <>{t.project} · </>}Sprint {t.sprint} · {TYPE_LABEL[t.task_type] ?? t.task_type}
          {t.blocked_by.length > 0 && t.status !== "done" && <span className="text-amber-700"> · waiting on {t.blocked_by.join(", ")}</span>}
        </p>
      </div>
      <div className="hidden w-32 sm:block">
        <div className={cx("mb-1 text-right text-xs tabular-nums", over ? "font-medium text-rose-600" : "text-zinc-500")}>
          {hours(t.actual_hours)} / {hours(t.planned_hours)}
        </div>
        <Progress value={t.actual_hours} max={t.planned_hours} tone={over ? "danger" : t.status === "done" ? "success" : "brand"} />
      </div>
      <Badge tone={STATUS_TONE[t.status]} dot>
        {STATUS_LABEL[t.status]}
      </Badge>
    </button>
  );
}
