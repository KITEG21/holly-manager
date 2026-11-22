import { Children, isValidElement, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { cx } from "./ui";

/** Id de ancla para un encabezado; la misma función resuelve las secciones citadas. */
export function slugify(text: string): string {
  return text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-");
}

function textOf(node: ReactNode): string {
  return Children.toArray(node)
    .map((c) => (typeof c === "string" || typeof c === "number" ? String(c) : isValidElement<{ children?: ReactNode }>(c) ? textOf(c.props.children) : ""))
    .join("");
}

const heading =
  (Tag: "h2" | "h3" | "h4") =>
  ({ children }: { children?: ReactNode }) => (
    <Tag id={slugify(textOf(children))} className="scroll-mt-24">
      {children}
    </Tag>
  );

/** Markdown con tablas (GFM), encabezados enlazables y, opcionalmente, citas [C1] convertidas en botones. */
export default function Markdown({
  children,
  onCite,
  className = "",
}: {
  children: string;
  onCite?: (id: number) => void;
  className?: string;
}) {
  const source = onCite ? children.replace(/\[C(\d+)\]/g, "[C$1](#cite-$1)") : children;
  const components: Components = {
    h2: heading("h2"),
    h3: heading("h3"),
    h4: heading("h4"),
    a: ({ href, children: c }) => {
      const cite = href?.match(/^#cite-(\d+)$/);
      if (cite && onCite) {
        return (
          <button
            type="button"
            onClick={() => onCite(Number(cite[1]))}
            className="mx-0.5 inline-flex h-5 items-center rounded-md bg-brand-100 px-1.5 align-baseline text-[11px] font-semibold text-brand-700 no-underline hover:bg-brand-200"
          >
            {cite[1]}
          </button>
        );
      }
      return (
        <a href={href} target={href?.startsWith("http") ? "_blank" : undefined} rel="noreferrer">
          {c}
        </a>
      );
    },
  };
  return (
    <div className={cx("prose prose-zinc max-w-none prose-headings:font-semibold prose-headings:tracking-tight prose-a:text-brand-700 prose-strong:text-zinc-900 prose-code:rounded prose-code:bg-zinc-100 prose-code:px-1 prose-code:py-0.5 prose-code:font-normal prose-code:before:content-none prose-code:after:content-none prose-th:text-zinc-700", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {source}
      </ReactMarkdown>
    </div>
  );
}
