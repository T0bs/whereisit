import React, { useState } from "react";
import { useSearch } from "../queries";

const MODES = [
  { id: "keyword", label: "Keyword" },
  { id: "semantic", label: "Semantic" },
  { id: "hybrid", label: "Hybrid" },
];

export default function SearchPanel({ onSelect }) {
  const [q, setQ] = useState("");
  const [mode, setMode] = useState("keyword");
  const [submitted, setSubmitted] = useState(null);

  const { data: results = [], isFetching, error } = useSearch(submitted, {
    enabled: !!submitted,
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    const trimmed = q.trim();
    setSubmitted(trimmed ? { q: trimmed, mode, limit: 30 } : null);
  };

  return (
    <div className="max-w-3xl space-y-4">
      <form onSubmit={handleSubmit} className="space-y-2">
        <div className="flex gap-2">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="search…"
            className="flex-1 px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
          />
          <button
            type="submit"
            className="px-4 py-2 bg-slate-900 text-white rounded-md text-sm hover:bg-slate-700"
          >
            Search
          </button>
        </div>
        <div className="flex items-center gap-1 text-sm">
          <span className="text-slate-500 mr-2">mode:</span>
          {MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              onClick={() => setMode(m.id)}
              className={
                "px-2.5 py-1 rounded-md text-xs " +
                (mode === m.id
                  ? "bg-slate-900 text-white"
                  : "bg-white border border-slate-200 text-slate-700 hover:bg-slate-100")
              }
            >
              {m.label}
            </button>
          ))}
        </div>
      </form>

      {error && (
        <div className="px-3 py-2 text-sm rounded-md bg-red-50 text-red-700 border border-red-200">
          {error.message}
        </div>
      )}

      {!submitted && (
        <p className="text-sm text-slate-500">
          Enter a query and pick a mode. <strong>Keyword</strong> is FULLTEXT;
          <strong> semantic</strong> needs Ollama embeddings (run
          <code className="px-1 mx-1 bg-slate-100 rounded">scripts/wii_embed</code>);
          <strong> hybrid</strong> fuses both via RRF.
        </p>
      )}

      {submitted && isFetching && <p className="text-sm text-slate-500">Searching…</p>}

      {submitted && !isFetching && results.length === 0 && !error && (
        <p className="text-sm text-slate-500">No matches.</p>
      )}

      <ul className="divide-y divide-slate-200 border border-slate-200 rounded-md bg-white">
        {results.map((r) => (
          <li
            key={r.id}
            onClick={() => onSelect(r.id)}
            className="px-3 py-2 cursor-pointer hover:bg-slate-50"
          >
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="font-medium text-sm truncate">{r.name}</div>
                <div className="text-xs text-slate-500 truncate">
                  {r.path?.length > 0
                    ? r.path.map((p) => p.name).join(" / ")
                    : "(root)"}
                </div>
              </div>
              <div className="flex items-center gap-2 text-xs text-slate-500 shrink-0">
                <span className="px-1.5 py-0.5 rounded bg-slate-100 uppercase text-[10px]">
                  {r.kind?.slug}
                </span>
                {typeof r.score === "number" && (
                  <span className="font-mono">{r.score.toFixed(3)}</span>
                )}
              </div>
            </div>
            {r.match_reason && (
              <div className="text-[11px] text-slate-400 mt-0.5">{r.match_reason}</div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
