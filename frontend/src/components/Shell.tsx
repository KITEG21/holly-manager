import { useQuery } from "@tanstack/react-query";
import {
  BarChart3,
  CalendarClock,
  FolderKanban,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Menu,
  Settings2,
  ShieldAlert,
  Sparkles,
  Users,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { api, type Escalation } from "../api";
import { useAuth } from "../auth";
import { Avatar, cx } from "./ui";
import { TaskDrawerProvider, TimerProvider, TimerWidget } from "./work";

interface Item {
  to: string;
  label: string;
  icon: ReactNode;
  end?: boolean;
  badge?: number;
}

function today() {
  const text = new Date().toLocaleDateString("en-US", { weekday: "long", day: "numeric", month: "long" });
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function Logo({ dark = false }: { dark?: boolean }) {
  return (
    <span className="flex items-center gap-2">
      <span className="grid size-8 place-items-center rounded-lg bg-gradient-to-br from-brand-500 to-fuchsia-500 text-white shadow-sm">
        <Sparkles className="size-4" />
      </span>
      <span className={cx("text-[15px] font-semibold tracking-tight", dark ? "text-white" : "text-zinc-900")}>Holly</span>
    </span>
  );
}

function NavSection({ title, items, onNavigate }: { title: string; items: Item[]; onNavigate: () => void }) {
  return (
    <div>
      <p className="mb-1 px-3 text-[11px] font-medium tracking-wider text-zinc-500 uppercase">{title}</p>
      <ul className="space-y-0.5">
        {items.map((i) => (
          <li key={i.to}>
            <NavLink
              to={i.to}
              end={i.end}
              onClick={onNavigate}
              className={({ isActive }) =>
                cx(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition [&>svg]:size-4",
                  isActive ? "bg-white/10 text-white" : "text-zinc-400 hover:bg-white/5 hover:text-zinc-100",
                )
              }
            >
              {i.icon}
              <span className="flex-1">{i.label}</span>
              {!!i.badge && <span className="rounded-full bg-rose-500 px-1.5 text-[10px] font-semibold text-white">{i.badge}</span>}
            </NavLink>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const isAdmin = user?.role === "admin";
  const escalations = useQuery({
    queryKey: ["escalations", "open"],
    queryFn: () => api<Escalation[]>("/api/escalations?status=open"),
    enabled: isAdmin,
    refetchInterval: 15_000,
  });

  const work: Item[] = [
    { to: "/dev", label: "Dashboard", icon: <LayoutDashboard />, end: true },
    { to: "/dev/tasks", label: "My tasks", icon: <ListChecks /> },
    { to: "/dev/projects", label: "Projects", icon: <FolderKanban /> },
    { to: "/dev/timesheet", label: "Timesheet", icon: <CalendarClock /> },
    { to: "/dev/reports", label: "Reports", icon: <BarChart3 /> },
  ];
  const sales: Item[] = [
    { to: "/admin/leads", label: "Clients", icon: <Users /> },
    { to: "/admin/escalations", label: "Escalations", icon: <ShieldAlert />, badge: escalations.data?.length },
    { to: "/admin/config", label: "Settings", icon: <Settings2 /> },
  ];

  const sidebar = (
    <div className="flex h-full flex-col bg-zinc-950 px-3 py-5">
      <div className="px-3">
        <Logo dark />
      </div>
      <nav className="mt-8 flex-1 space-y-6 overflow-y-auto">
        <NavSection title="Work" items={work} onNavigate={() => setOpen(false)} />
        {isAdmin && <NavSection title="Sales" items={sales} onNavigate={() => setOpen(false)} />}
      </nav>
      <div className="mt-4 flex items-center gap-3 rounded-xl bg-white/5 p-3">
        <Avatar name={user?.name} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-white">{user?.name}</p>
          <p className="truncate text-xs text-zinc-400">{isAdmin ? "Admin" : "Developer"}</p>
        </div>
        <button onClick={logout} className="rounded-lg p-1.5 text-zinc-400 hover:bg-white/10 hover:text-white" title="Sign out" aria-label="Sign out">
          <LogOut className="size-4" />
        </button>
      </div>
    </div>
  );

  return (
    <TimerProvider>
      <TaskDrawerProvider>
        <div className="min-h-screen lg:pl-64">
          <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 lg:block">{sidebar}</aside>
          {open && (
            <div className="fixed inset-0 z-40 lg:hidden">
              <div className="absolute inset-0 bg-zinc-950/40" onClick={() => setOpen(false)} />
              <aside className="animate-fade-in relative h-full w-64">{sidebar}</aside>
            </div>
          )}
          <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-zinc-200/70 bg-zinc-50/80 px-4 backdrop-blur sm:px-6">
            <button className="rounded-lg p-1.5 text-zinc-600 hover:bg-zinc-200/60 lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu">
              <Menu className="size-5" />
            </button>
            <span className="text-sm text-zinc-500">{today()}</span>
            <div className="ml-auto">
              <TimerWidget />
            </div>
          </header>
          <main key={location.pathname} className="animate-fade-in mx-auto max-w-7xl px-4 py-8 sm:px-6">
            {children}
          </main>
        </div>
      </TaskDrawerProvider>
    </TimerProvider>
  );
}
