/** Gráficas en HTML: marcas finas con extremo redondeado de 4 px, separación de 2 px entre segmentos,
 * leyenda + tooltip al pasar el ratón, y siempre una vista de tabla equivalente. */
import { useState, type ReactNode } from "react";
import { cx } from "./ui";

// Paleta categórica validada (orden fijo; nunca se recicla un color para otra serie)
export const SERIES = ["var(--color-series-1)", "var(--color-series-2)", "var(--color-series-3)"];

export function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-600">
      {items.map((i) => (
        <li key={i.label} className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm" style={{ background: i.color }} />
          {i.label}
        </li>
      ))}
    </ul>
  );
}

function Tooltip({ children }: { children: ReactNode }) {
  return (
    <div className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-2 w-max max-w-56 -translate-x-1/2 rounded-lg bg-zinc-900 px-3 py-2 text-xs text-white shadow-pop">
      {children}
    </div>
  );
}

function niceMax(v: number) {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  return Math.ceil(v / p) * p;
}

/** Columnas apiladas: una columna por categoría del eje X, un segmento por serie. */
export function StackedColumns({
  categories,
  series,
  values,
  format,
  height = 220,
}: {
  categories: string[];
  series: { label: string; color: string }[];
  values: number[][]; // values[categoría][serie]
  format: (v: number) => string;
  height?: number;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const max = niceMax(Math.max(0, ...values.map((row) => row.reduce((a, b) => a + b, 0))));
  const ticks = [0, max / 2, max];
  return (
    <div>
      <div className="relative flex gap-3" style={{ height }}>
        <div className="flex flex-col justify-between pb-6 text-right text-[11px] text-zinc-400 tabular-nums">
          {[...ticks].reverse().map((t) => (
            <span key={t}>{format(t)}</span>
          ))}
        </div>
        <div className="relative flex-1">
          <div className="absolute inset-x-0 top-0 bottom-6 flex flex-col justify-between">
            {ticks.map((t) => (
              <div key={t} className="border-t border-zinc-100" />
            ))}
          </div>
          <div className="absolute inset-x-0 top-0 bottom-6 flex items-end justify-around gap-2">
            {values.map((row, ci) => {
              const total = row.reduce((a, b) => a + b, 0);
              return (
                <div
                  key={ci}
                  className="relative flex h-full w-full max-w-12 flex-col-reverse items-stretch justify-start gap-[2px]"
                  onMouseEnter={() => setHover(ci)}
                  onMouseLeave={() => setHover(null)}
                >
                  {row.map((v, si) =>
                    v > 0 ? (
                      <div
                        key={si}
                        className={cx("w-full transition-opacity", si === row.findLastIndex((x) => x > 0) && "rounded-t-[4px]", hover != null && hover !== ci && "opacity-40")}
                        style={{ height: `${(v / max) * 100}%`, background: series[si]!.color }}
                      />
                    ) : null,
                  )}
                  {hover === ci && (
                    <Tooltip>
                      <div className="mb-1 font-medium">{categories[ci]}</div>
                      {series.map((s, si) => (
                        <div key={s.label} className="flex items-center justify-between gap-4">
                          <span className="flex items-center gap-1.5">
                            <span className="size-2 rounded-sm" style={{ background: s.color }} />
                            {s.label}
                          </span>
                          <span className="tabular-nums">{format(row[si] ?? 0)}</span>
                        </div>
                      ))}
                      <div className="mt-1 flex justify-between border-t border-white/20 pt-1 font-medium">
                        <span>Total</span>
                        <span className="tabular-nums">{format(total)}</span>
                      </div>
                    </Tooltip>
                  )}
                </div>
              );
            })}
          </div>
          <div className="absolute inset-x-0 bottom-0 flex h-6 items-end justify-around gap-2 border-t border-zinc-300">
            {categories.map((c) => (
              <span key={c} className="w-full max-w-12 truncate text-center text-[11px] text-zinc-500">
                {c}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/** Barras horizontales emparejadas (p. ej. planificado frente a real) por categoría. */
export function PairedBars({
  rows,
  series,
  format,
  note,
}: {
  rows: { label: string; values: [number, number]; extra?: ReactNode }[];
  series: [{ label: string; color: string }, { label: string; color: string }];
  format: (v: number) => string;
  note?: (row: { values: [number, number] }) => ReactNode;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const max = niceMax(Math.max(0, ...rows.flatMap((r) => r.values)));
  return (
    <div className="space-y-4">
      {rows.map((r, i) => (
        <div
          key={r.label}
          className={cx("relative grid grid-cols-[110px_1fr_auto] items-center gap-3 transition-opacity", hover != null && hover !== i && "opacity-40")}
          onMouseEnter={() => setHover(i)}
          onMouseLeave={() => setHover(null)}
        >
          <span className="truncate text-sm text-zinc-700">{r.label}</span>
          <div className="relative flex flex-col gap-[2px] border-l border-zinc-300">
            {r.values.map((v, si) => (
              <div key={si} className="flex items-center gap-2">
                <div className="h-3 rounded-r-[4px]" style={{ width: `${(v / max) * 100}%`, minWidth: v > 0 ? 2 : 0, background: series[si]!.color }} />
              </div>
            ))}
            {hover === i && (
              <Tooltip>
                <div className="mb-1 font-medium">{r.label}</div>
                {series.map((s, si) => (
                  <div key={s.label} className="flex justify-between gap-4">
                    <span className="flex items-center gap-1.5">
                      <span className="size-2 rounded-sm" style={{ background: s.color }} />
                      {s.label}
                    </span>
                    <span className="tabular-nums">{format(r.values[si]!)}</span>
                  </div>
                ))}
              </Tooltip>
            )}
          </div>
          <span className="w-20 text-right text-xs text-zinc-500">{note?.(r) ?? r.extra}</span>
        </div>
      ))}
    </div>
  );
}

/** Tabla equivalente a una gráfica, para lectura precisa y accesibilidad. */
export function DataTable({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-100 text-xs text-zinc-500">
            {head.map((h, i) => (
              <th key={h} className={cx("py-2 font-medium", i === 0 ? "text-left" : "text-right")}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100">
          {rows.map((r, i) => (
            <tr key={i}>
              {r.map((c, j) => (
                <td key={j} className={cx("py-2 tabular-nums", j === 0 ? "text-left text-zinc-800" : "text-right text-zinc-600")}>
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
