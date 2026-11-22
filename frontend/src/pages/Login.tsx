import { CalendarClock, KanbanSquare, MessagesSquare, ShieldCheck } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { homeFor, useAuth } from "../auth";
import { Logo } from "../components/Shell";
import { Button, ErrorText, Input } from "../components/ui";

const FEATURES = [
  { icon: <MessagesSquare />, title: "From chat to scope", text: "Tell us your idea and we turn it into clear requirements." },
  { icon: <KanbanSquare />, title: "Backlog and sprints", text: "Every task, with its estimate and its owner." },
  { icon: <CalendarClock />, title: "Actual time, not guesses", text: "Timesheet, timer and a forecast that adjusts itself." },
  { icon: <ShieldCheck />, title: "No surprises", text: "Prices and terms are calculated, never improvised." },
];

export function AuthLayout({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      <aside className="console-grid relative hidden overflow-hidden bg-ink p-12 lg:flex lg:flex-col">
        <div className="pointer-events-none absolute -top-40 -right-24 size-[30rem] rounded-full bg-brand-500/25 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-32 -left-24 size-[24rem] rounded-full bg-accent-500/20 blur-3xl" />
        {/* Marca de agua: la baya del logo a gran tamaño */}
        <div className="pointer-events-none absolute top-1/2 -right-40 size-[26rem] -translate-y-1/2 rounded-full border border-white/[0.06]" />
        <div className="pointer-events-none absolute top-1/2 -right-20 size-[18rem] -translate-y-1/2 rounded-full border border-white/[0.06]" />
        <div className="relative">
          <Logo dark />
        </div>
        <div className="relative mt-auto max-w-md pt-16">
          <p className="mb-5 inline-flex items-center gap-2 rounded-md bg-white/[0.06] px-2.5 py-1 font-mono text-[11px] tracking-[0.12em] text-brand-300 uppercase ring-1 ring-white/10"><span className="size-1.5 rounded-full bg-brand-400 shadow-[0_0_8px_#34cfa3]" /> For software studios</p>
          <h2 className="text-[44px] leading-[1.05] font-semibold tracking-[-0.035em] text-white">
            From the first idea to the <span className="text-gradient">last hour logged.</span>
          </h2>
          <ul className="mt-12 space-y-6 border-t border-white/10 pt-8">
            {FEATURES.map((f) => (
              <li key={f.title} className="flex gap-4">
                <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-white/[0.06] text-brand-300 ring-1 ring-white/10 [&>svg]:size-[18px]">
                  {f.icon}
                </span>
                <div>
                  <p className="text-sm font-medium text-white">{f.title}</p>
                  <p className="mt-0.5 text-sm text-zinc-400">{f.text}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </aside>
      <main className="flex items-center justify-center px-6 py-12">
        <div className="animate-fade-in w-full max-w-sm">
          <div className="mb-10 lg:hidden">
            <Logo />
          </div>
          <h1 className="text-[30px] leading-tight font-semibold tracking-[-0.025em]">{title}</h1>
          <p className="mt-2 mb-8 text-sm text-zinc-500">{subtitle}</p>
          {children}
        </div>
      </main>
    </div>
  );
}

export default function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);

  if (user) return <Navigate to={homeFor(user.role)} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setPending(true);
    setError(null);
    try {
      const u = await login(email, password);
      navigate(homeFor(u.role), { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setPending(false);
    }
  }

  return (
    <AuthLayout title="Welcome back" subtitle="Sign in to continue. Clients and team members both sign in here.">
      <form className="space-y-4" onSubmit={submit}>
        <Input label="Email" type="email" autoComplete="email" placeholder="you@company.com" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <Input label="Password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        <Button type="submit" className="w-full" loading={pending}>
          Sign in
        </Button>
        <ErrorText error={error} />
      </form>
      <p className="mt-8 text-center text-sm text-zinc-500">
        Have a project in mind?{" "}
        <Link to="/register" className="font-medium text-brand-700 hover:underline">
          Create your account
        </Link>
      </p>
    </AuthLayout>
  );
}
