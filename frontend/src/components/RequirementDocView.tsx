import type { RequirementDoc } from "../api";
import { Badge } from "./ui";

export default function RequirementDocView({ doc }: { doc: RequirementDoc }) {
  const open = doc.ambiguities.filter((a) => a.status === "open");
  return (
    <div className="space-y-4 text-sm">
      {open.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
          <div className="mb-1 font-medium text-amber-900">Open questions</div>
          <ul className="list-disc pl-5 text-amber-900">
            {open.map((a) => (
              <li key={a.id}>{a.question}</li>
            ))}
          </ul>
        </div>
      )}

      {doc.epics.map((epic) => (
        <div key={epic.id}>
          <h3 className="font-semibold text-zinc-800">
            {epic.id} · {epic.title}
          </h3>
          {epic.description && <p className="text-zinc-500">{epic.description}</p>}
          <ul className="mt-2 space-y-2">
            {doc.stories
              .filter((s) => s.epic_id === epic.id)
              .map((s) => (
                <li key={s.id} className="rounded-lg border border-zinc-200 p-2">
                  <div>
                    <span className="mr-1 font-mono text-xs text-brand-700">{s.id}</span>
                    As <b>{s.as_a}</b>, I want {s.i_want}
                    {s.so_that && <> so that {s.so_that}</>}.
                  </div>
                  {s.acceptance_criteria.length > 0 && (
                    <ul className="mt-1 list-disc pl-5 text-zinc-600">
                      {s.acceptance_criteria.map((ac, i) => (
                        <li key={i}>{ac}</li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
          </ul>
        </div>
      ))}

      {doc.nfrs.length > 0 && (
        <div>
          <h3 className="font-semibold text-zinc-800">Non-functional requirements</h3>
          <ul className="mt-1 space-y-1">
            {doc.nfrs.map((n) => (
              <li key={n.id}>
                <Badge>{n.category}</Badge> {n.text}
              </li>
            ))}
          </ul>
        </div>
      )}

      {doc.out_of_scope.length > 0 && (
        <div>
          <h3 className="font-semibold text-zinc-800">Out of scope</h3>
          <ul className="list-disc pl-5 text-zinc-600">
            {doc.out_of_scope.map((o) => (
              <li key={o}>{o}</li>
            ))}
          </ul>
        </div>
      )}

      {doc.summary && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3">
          <div className="mb-1 font-medium text-emerald-900">Proposed summary</div>
          <p className="text-emerald-900">{doc.summary}</p>
        </div>
      )}

      {!doc.epics.length && <p className="text-zinc-500">The document will fill in as the conversation goes on.</p>}
    </div>
  );
}
