import { Loader2, X } from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

export const cx = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(" ");

// --- Superficies ---------------------------------------------------------------------------------

export function Card({
  title,
  description,
  actions,
  children,
  className = "",
  padded = true,
}: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return (
    <section className={cx("rounded-xl bg-white shadow-card ring-1 ring-zinc-200", !padded && "overflow-hidden", className)}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-3 border-b border-zinc-100 px-5 py-4">
          <div className="min-w-0">
            <h2 className="text-[15px] leading-snug font-semibold tracking-tight text-zinc-900">{title}</h2>
            {description && <p className="mt-0.5 text-xs text-zinc-500">{description}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={padded ? "p-5" : ""}>{children}</div>
    </section>
  );
}

export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  eyebrow?: ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        {eyebrow && <p className="mb-2 font-mono text-[11px] font-medium tracking-[0.12em] text-brand-600 uppercase">{eyebrow}</p>}
        <h1 className="text-[30px] leading-[1.15] font-semibold tracking-[-0.025em] text-zinc-900">{title}</h1>
        {description && <p className="mt-2 max-w-2xl text-sm text-zinc-500">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function StatCard({
  icon,
  label,
  value,
  hint,
  tone = "default",
}: {
  icon?: ReactNode;
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "default" | "danger" | "success";
}) {
  return (
    <div className="rounded-xl bg-white p-5 shadow-card ring-1 ring-zinc-200">
      <div className="flex items-center gap-2 text-xs font-medium text-zinc-500">
        {icon && <span className="grid size-7 place-items-center rounded-lg bg-brand-50 text-brand-700 ring-1 ring-brand-100 [&>svg]:size-3.5">{icon}</span>}
        {label}
      </div>
      <div
        className={cx(
          "mt-3 text-[30px] leading-none font-semibold tracking-[-0.03em] tabular-nums",
          tone === "danger" ? "text-rose-700" : tone === "success" ? "text-brand-600" : "text-zinc-900",
        )}
      >
        {value}
      </div>
      {hint && <div className="mt-1 text-xs text-zinc-500">{hint}</div>}
    </div>
  );
}

export function EmptyState({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-zinc-300 bg-white/60 px-6 py-12 text-center">
      {icon && <div className="mb-3 grid size-11 place-items-center rounded-xl bg-brand-50 text-brand-600 ring-1 ring-brand-100 [&>svg]:size-5">{icon}</div>}
      <p className="text-base font-semibold text-zinc-800">{title}</p>
      {children && <div className="mt-1 max-w-sm text-sm text-zinc-500">{children}</div>}
    </div>
  );
}

// --- Controles -----------------------------------------------------------------------------------

type Variant = "primary" | "secondary" | "ghost" | "danger";
const VARIANTS: Record<Variant, string> = {
  primary: "bg-brand-600 text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.15)] hover:bg-brand-700 focus-visible:outline-brand-500",
  secondary: "bg-white text-zinc-700 ring-1 ring-zinc-300 hover:bg-zinc-50 hover:text-zinc-900 hover:ring-zinc-400",
  ghost: "text-zinc-600 hover:bg-zinc-200/60 hover:text-zinc-900",
  danger: "bg-rose-700 text-white hover:bg-rose-800",
};

export function Button({
  variant = "primary",
  size = "md",
  icon,
  loading = false,
  className = "",
  children,
  disabled,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: "sm" | "md";
  icon?: ReactNode;
  loading?: boolean;
}) {
  return (
    <button
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition active:translate-y-px focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-50 [&>svg]:size-4",
        size === "sm" ? "h-8 px-3 text-xs" : "h-9 px-4 text-sm",
        VARIANTS[variant],
        className,
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? <Loader2 className="animate-spin" /> : icon}
      {children}
    </button>
  );
}

const FIELD =
  "w-full rounded-lg border-0 bg-white px-3 py-2 text-sm text-zinc-900 ring-1 ring-zinc-300 placeholder:text-zinc-400 focus:ring-2 focus:ring-brand-500 focus:outline-none disabled:bg-zinc-100 disabled:text-zinc-500";

function Labelled({ label, hint, children }: { label?: string; hint?: string; children: ReactNode }) {
  if (!label) return <>{children}</>;
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-medium text-zinc-700">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-zinc-500">{hint}</span>}
    </label>
  );
}

export function Input({ label, hint, className = "", ...props }: InputHTMLAttributes<HTMLInputElement> & { label?: string; hint?: string }) {
  return (
    <Labelled label={label} hint={hint}>
      <input className={cx(FIELD, className)} {...props} />
    </Labelled>
  );
}

export function Select({
  label,
  className = "",
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & { label?: string }) {
  return (
    <Labelled label={label}>
      <select className={cx(FIELD, "pr-8", className)} {...props}>
        {children}
      </select>
    </Labelled>
  );
}

export function Textarea({ label, className = "", ...props }: TextareaHTMLAttributes<HTMLTextAreaElement> & { label?: string }) {
  return (
    <Labelled label={label}>
      <textarea className={cx(FIELD, className)} {...props} />
    </Labelled>
  );
}

/** Selector segmentado (pestañas compactas o filtros). */
export function Segmented<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: ReactNode }[];
}) {
  return (
    <div className="inline-flex rounded-lg bg-zinc-200/70 p-1" role="tablist">
      {options.map((o) => (
        <button
          key={o.value}
          role="tab"
          aria-selected={o.value === value}
          onClick={() => onChange(o.value)}
          className={cx(
            "rounded-md px-3 py-1.5 text-xs font-medium transition",
            o.value === value ? "bg-white text-zinc-900 shadow-[0_1px_2px_rgb(14_18_16/0.12)]" : "text-zinc-600 hover:text-zinc-900",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// --- Indicadores ---------------------------------------------------------------------------------

const BADGE_TONES = {
  slate: "bg-zinc-100 text-zinc-700 ring-zinc-200",
  green: "bg-brand-50 text-brand-700 ring-brand-200",
  amber: "bg-amber-50 text-amber-800 ring-amber-200",
  red: "bg-rose-50 text-rose-700 ring-rose-200",
  indigo: "bg-brand-50 text-brand-700 ring-brand-200",
  blue: "bg-accent-50 text-accent-700 ring-accent-200",
};
const DOT_TONES = {
  slate: "bg-zinc-400",
  green: "bg-brand-500",
  amber: "bg-amber-500",
  red: "bg-rose-500",
  indigo: "bg-brand-500",
  blue: "bg-accent-500",
};
export type Tone = keyof typeof BADGE_TONES;

export function Badge({ tone = "slate", dot = false, children }: { tone?: Tone; dot?: boolean; children: ReactNode }) {
  return (
    <span className={cx("inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset", BADGE_TONES[tone])}>
      {dot && <span className={cx("size-1.5 rounded-full", DOT_TONES[tone])} />}
      {children}
    </span>
  );
}

export function Progress({ value, max, tone = "brand", className = "" }: { value: number; max: number; tone?: "brand" | "danger" | "success"; className?: string }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  const bar = tone === "danger" ? "bg-rose-500" : tone === "success" ? "bg-brand-500" : "bg-accent-500";
  return (
    <div className={cx("h-1.5 overflow-hidden rounded-full bg-zinc-200/70", className)} role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
      <div className={cx("h-full rounded-full transition-all", bar)} style={{ width: `${pct}%` }} />
    </div>
  );
}

// Tonos de la paleta para los avatares: cada persona conserva siempre el mismo
const AVATAR_TONES = ["bg-brand-600", "bg-accent-600", "bg-[#5b6cf0]", "bg-[#7c5cd6]", "bg-zinc-600", "bg-brand-800"];

function toneFor(name: string): string {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return AVATAR_TONES[h % AVATAR_TONES.length]!;
}

export function Avatar({ name, size = "md" }: { name?: string | null; size?: "sm" | "md" }) {
  const initials = (name ?? "?")
    .split(/[\s@.]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join("");
  return (
    <span
      title={name ?? undefined}
      className={cx(
        "inline-grid shrink-0 place-items-center rounded-full font-semibold text-white ring-2 ring-white",
        toneFor(name ?? "?"),
        size === "sm" ? "size-6 text-[10px]" : "size-8 text-xs",
      )}
    >
      {initials}
    </span>
  );
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-10 text-sm text-zinc-500">
      <Loader2 className="size-4 animate-spin" /> {label}
    </div>
  );
}

export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  return <p className="text-sm text-rose-600">{error instanceof Error ? error.message : String(error)}</p>;
}

// --- Panel lateral -------------------------------------------------------------------------------

export function Drawer({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-ink/40 backdrop-blur-[2px]" onClick={onClose} />
      <aside className="animate-slide-in relative flex h-full w-full max-w-lg flex-col bg-white shadow-pop">
        <header className="flex items-start justify-between gap-3 border-b border-zinc-100 px-6 py-4">
          <div className="min-w-0 flex-1">{title}</div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700" aria-label="Close">
            <X className="size-4" />
          </button>
        </header>
        <div className="flex-1 overflow-y-auto px-6 py-5">{children}</div>
      </aside>
    </div>
  );
}

// --- Notificaciones ------------------------------------------------------------------------------

interface Toast {
  id: number;
  message: string;
  tone: "success" | "error" | "info";
}
const ToastContext = createContext<(message: string, tone?: Toast["tone"]) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((message: string, tone: Toast["tone"] = "info") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, message, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4000);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed right-4 bottom-4 z-50 flex w-80 flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cx(
              "animate-fade-in pointer-events-auto rounded-xl px-4 py-3 text-sm shadow-pop ring-1",
              t.tone === "error"
                ? "bg-rose-50 text-rose-800 ring-rose-200"
                : t.tone === "success"
                  ? "bg-emerald-50 text-emerald-800 ring-emerald-200"
                  : "bg-zinc-900 text-white ring-zinc-900",
            )}
          >
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);

export const errorMessage = (e: unknown) => (e instanceof Error ? e.message : String(e));
