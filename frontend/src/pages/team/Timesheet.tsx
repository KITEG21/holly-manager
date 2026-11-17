import { useQuery } from "@tanstack/react-query";
import { CalendarClock, ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { useState } from "react";
import { api } from "../../api";
import { Button, Card, cx, Drawer, EmptyState, errorMessage, Input, PageHeader, Select, Spinner, useToast } from "../../components/ui";
import { useTaskDrawer } from "../../components/work";
import { hours, isoDate, parseDate, useTaskActions, type Task, type Timesheet as Sheet } from "../../dev";

function shiftWeek(iso: string, weeks: number) {
  const d = parseDate(iso);
  d.setDate(d.getDate() + weeks * 7);
  return isoDate(d);
}

export default function Timesheet() {
  const [week, setWeek] = useState(isoDate(new Date()));
  const [adding, setAdding] = useState<string | null>(null);
  const { openTask } = useTaskDrawer();
  const q = useQuery({ queryKey: ["timesheet", week], queryFn: () => api<Sheet>(`/api/dev/timesheet?week_start=${week}`) });
  const s = q.data;
  const today = isoDate(new Date());
  const isCurrent = s ? s.days.includes(today) : true;

  const range = s
    ? `${parseDate(s.days[0]!).toLocaleDateString("en-US", { day: "numeric", month: "short" })} – ${parseDate(s.days[6]!).toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" })}`
    : "";

  return (
    <>
      <PageHeader
        title="Timesheet"
        description="Your hours for the week, by task and day."
        actions={
          <>
            <div className="flex items-center rounded-lg bg-white shadow-sm ring-1 ring-zinc-200">
              <button className="p-2 text-zinc-500 hover:text-zinc-900" onClick={() => setWeek(shiftWeek(week, -1))} aria-label="Previous week">
                <ChevronLeft className="size-4" />
              </button>
              <span className="min-w-44 px-2 text-center text-sm font-medium">{range}</span>
              <button
                className="p-2 text-zinc-500 hover:text-zinc-900 disabled:opacity-30"
                onClick={() => setWeek(shiftWeek(week, 1))}
                disabled={isCurrent}
                aria-label="Next week"
              >
                <ChevronRight className="size-4" />
              </button>
            </div>
            {!isCurrent && (
              <Button variant="secondary" onClick={() => setWeek(today)}>
                Today
              </Button>
            )}
            <Button icon={<Plus />} onClick={() => setAdding(isCurrent ? today : s?.days[4] ?? today)}>
              Add time
            </Button>
          </>
        }
      />

      {!s ? (
        <Spinner />
      ) : s.rows.length === 0 ? (
        <EmptyState icon={<CalendarClock />} title="No hours this week">
          Log time from a task, use the timer, or click "Add time".
        </EmptyState>
      ) : (
        <Card padded={false}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead>
                <tr className="border-b border-zinc-100 text-xs text-zinc-500">
                  <th className="px-5 py-3 text-left font-medium">Task</th>
                  {s.days.map((d) => {
                    const date = parseDate(d);
                    return (
                      <th key={d} className={cx("w-20 px-2 py-3 text-center font-medium", d === today && "text-brand-700")}>
                        <div className="capitalize">{date.toLocaleDateString("en-US", { weekday: "short" })}</div>
                        <div className={cx("text-base font-semibold", d === today ? "text-brand-700" : "text-zinc-800")}>{date.getDate()}</div>
                      </th>
                    );
                  })}
                  <th className="w-20 px-4 py-3 text-right font-medium">Total</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {s.rows.map((r) => (
                  <tr key={r.task_id} className="hover:bg-zinc-50/60">
                    <td className="px-5 py-3">
                      <button onClick={() => openTask(r.task_id)} className="text-left">
                        <span className="mr-2 font-mono text-xs font-medium text-brand-700">{r.key}</span>
                        <span className="font-medium text-zinc-800 hover:underline">{r.title}</span>
                        <div className="text-xs text-zinc-500">{r.project}</div>
                      </button>
                    </td>
                    {r.hours.map((h, i) => (
                      <td key={i} className={cx("px-2 py-3 text-center tabular-nums", s.days[i] === today && "bg-brand-50/50")}>
                        {h > 0 ? <span className="rounded-md bg-brand-100 px-2 py-1 text-xs font-semibold text-brand-700">{h}</span> : <span className="text-zinc-300">–</span>}
                      </td>
                    ))}
                    <td className="px-4 py-3 text-right font-semibold tabular-nums">{hours(r.total)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t border-zinc-200 bg-zinc-50 text-sm font-semibold">
                  <td className="px-5 py-3 text-zinc-600">Daily total</td>
                  {s.day_totals.map((t, i) => (
                    <td key={i} className={cx("px-2 py-3 text-center tabular-nums", t > 8 ? "text-amber-700" : "text-zinc-800")}>
                      {t > 0 ? t : <span className="text-zinc-300">–</span>}
                    </td>
                  ))}
                  <td className="px-4 py-3 text-right text-brand-700 tabular-nums">{hours(s.total)}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </Card>
      )}

      {adding && <AddHours key={adding} day={adding} onClose={() => setAdding(null)} />}
    </>
  );
}

function AddHours({ day, onClose }: { day: string; onClose: () => void }) {
  const toast = useToast();
  const { logTime } = useTaskActions();
  const tasks = useQuery({ queryKey: ["dev-tasks", "all"], queryFn: () => api<Task[]>("/api/dev/tasks") });
  const [taskId, setTaskId] = useState("");
  const [h, setH] = useState("");
  const [note, setNote] = useState("");
  const [date, setDate] = useState(day);
  const byProject = new Map<string, Task[]>();
  for (const t of tasks.data ?? []) {
    if (t.status === "done" || t.blocked_by.length > 0) continue;
    byProject.set(t.project, [...(byProject.get(t.project) ?? []), t]);
  }

  return (
    <Drawer open onClose={onClose} title={<h2 className="text-base font-semibold">Add time</h2>}>
      <form
        className="space-y-4"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await logTime.mutateAsync({ id: Number(taskId), hours: Number(h), note, workDate: date });
            toast("Time logged", "success");
            setH("");
            setNote("");
            onClose();
          } catch (err) {
            toast(errorMessage(err), "error");
          }
        }}
      >
        <Select label="Task" value={taskId} onChange={(e) => setTaskId(e.target.value)} required>
          <option value="">Choose a task…</option>
          {[...byProject].map(([project, ts]) => (
            <optgroup key={project} label={project}>
              {ts.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.key} · {t.title}
                </option>
              ))}
            </optgroup>
          ))}
        </Select>
        <div className="grid grid-cols-2 gap-3">
          <Input label="Day" type="date" value={date} max={isoDate(new Date())} onChange={(e) => setDate(e.target.value)} required />
          <Input label="Hours" type="number" step="0.25" min="0.25" max="24" value={h} onChange={(e) => setH(e.target.value)} required />
        </div>
        <Input label="Note (optional)" placeholder="What did you do?" value={note} onChange={(e) => setNote(e.target.value)} />
        <p className="text-xs text-zinc-500">Only open tasks with no pending dependencies are listed.</p>
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={logTime.isPending} disabled={!taskId || !h}>
            Log time
          </Button>
        </div>
      </form>
    </Drawer>
  );
}
