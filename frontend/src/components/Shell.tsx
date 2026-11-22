import { useQuery } from "@tanstack/react-query";
import {
  BarChart3,
  BookOpen,
  CalendarClock,
  FolderKanban,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Menu,
  Settings2,
  ShieldAlert,
  Users,
} from "lucide-react";
import { useId, useState, type ReactNode } from "react";
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

/** Marca de Holly: dos hojas de acebo en degradado jade y una baya cian. */
export function HollyMark({ className = "size-8", onDark = false }: { className?: string; onDark?: boolean }) {
  const id = useId();
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <defs>
        <linearGradient id={`${id}-leaf`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={onDark ? "#6ee4bf" : "#12b28a"} />
          <stop offset="1" stopColor={onDark ? "#12b28a" : "#0b735b"} />
        </linearGradient>
        <radialGradient id={`${id}-berry`} cx=".35" cy=".35" r=".8">
          <stop offset="0" stopColor="#a5f3fc" />
          <stop offset="1" stopColor="#06b6d4" />
        </radialGradient>
      </defs>
      <path d="M15 17C9 18 4.5 14.5 3.5 8.5 9.5 7.5 14 11 15 17Z" fill={`url(#${id}-leaf)`} />
      <path d="M17 17c6 1 10.5-2.5 11.5-8.5C22.5 7.5 18 11 17 17Z" fill={`url(#${id}-leaf)`} opacity=".7" />
      <path d="M15 17 7.5 10.5M17 17l7.5-6.5" stroke={onDark ? "#0b1210" : "#ffffff"} strokeWidth=".9" strokeLinecap="round" opacity=".45" />
      {onDark && <circle cx="16" cy="21.5" r="7" fill="#22d3ee" opacity=".18" />}
      <circle cx="16" cy="21.5" r="4.5" fill={`url(#${id}-berry)`} />
    </svg>
  );
}

export function Logo({ dark = false }: { dark?: boolean }) {
  return (
    <span className="flex items-center gap-2">
      <HollyMark onDark={dark} />
      <span className={cx("text-[19px] leading-none font-semibold tracking-[-0.03em]", dark ? "text-white" : "text-zinc-900")}>
        holly
      </span>
    </span>
  );
}

function NavSection({ title, items, onNavigate }: { title: string; items: Item[]; onNavigate: () => void }) {
  return (
    <div>
      <p className="mb-1.5 px-3 font-mono text-[10px] font-medium tracking-[0.14em] text-zinc-500 uppercase">{title}</p>
      <ul className="space-y-0.5">
        {items.map((i) => (
          <li key={i.to}>
            <NavLink
              to={i.to}
              end={i.end}
              onClick={onNavigate}
              className={({ isActive }) =>
                cx(
                  "relative flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition [&>svg]:size-4",
                  // Activo: fondo claro y una marca terracota a la izquierda
                  isActive
                    ? "bg-white/[0.07] text-white ring-1 ring-white/[0.06] before:absolute before:top-2 before:bottom-2 before:-left-3 before:w-1 before:rounded-r-full before:bg-brand-400 before:shadow-[0_0_12px_#34cfa3]"
                    : "text-zinc-400 hover:bg-white/5 hover:text-white",
                )
              }
            >
              {i.icon}
              <span className="flex-1">{i.label}</span>
              {!!i.badge && <span className="rounded-md bg-rose-500 px-1.5 font-mono text-[10px] font-semibold text-white">{i.badge}</span>}
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
    { to: "/dev/docs", label: "Documentation", icon: <BookOpen /> },
  ];
  const sales: Item[] = [
    { to: "/admin/leads", label: "Clients", icon: <Users /> },
    { to: "/admin/escalations", label: "Escalations", icon: <ShieldAlert />, badge: escalations.data?.length },
    { to: "/admin/config", label: "Settings", icon: <Settings2 /> },
  ];

  const sidebar = (
    <div className="console-grid relative flex h-full flex-col overflow-hidden bg-ink px-3 py-6">
      {/* Halo cálido decorativo */}
      <div className="pointer-events-none absolute -bottom-24 -left-16 size-72 rounded-full bg-brand-500/20 blur-3xl" />
      <div className="relative px-3">
        <Logo dark />
      </div>
      <nav className="relative mt-9 flex-1 space-y-7 overflow-y-auto">
        <NavSection title="Work" items={work} onNavigate={() => setOpen(false)} />
        {isAdmin && <NavSection title="Sales" items={sales} onNavigate={() => setOpen(false)} />}
      </nav>
      <div className="relative mt-4 flex items-center gap-3 rounded-xl bg-white/[0.05] p-3 ring-1 ring-white/10">
        <Avatar name={user?.name} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-white">{user?.name}</p>
          <p className="truncate font-mono text-[11px] text-zinc-400">{isAdmin ? "Admin" : "Developer"}</p>
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
              <div className="absolute inset-0 bg-ink/50" onClick={() => setOpen(false)} />
              <aside className="animate-fade-in relative h-full w-64">{sidebar}</aside>
            </div>
          )}
          <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-zinc-200/80 bg-paper/85 px-4 backdrop-blur sm:px-6">
            <button className="rounded-lg p-1.5 text-zinc-600 hover:bg-zinc-200/60 lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu">
              <Menu className="size-5" />
            </button>
            <span className="font-mono text-[11px] tracking-[0.12em] text-zinc-500 uppercase">{today()}</span>
            <div className="ml-auto">
              <TimerWidget />
            </div>
          </header>
          <main key={location.pathname.split("/").slice(0, 3).join("/")} className="animate-fade-in mx-auto max-w-7xl px-4 py-10 sm:px-8">
            {children}
          </main>
        </div>
      </TaskDrawerProvider>
    </TimerProvider>
  );
}
