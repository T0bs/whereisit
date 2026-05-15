import React, { useState } from "react";
import { useAsk } from "../queries";

export default function AskPanel({ onSelect }) {
  const [question, setQuestion] = useState("");
  const ask = useAsk();

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!question.trim()) return;
    ask.mutate({ question: question.trim() });
  };

  const result = ask.data;

  return (
    <div className="max-w-3xl space-y-4">
      <form onSubmit={handleSubmit} className="space-y-2">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="ask in plain English — e.g. 'where is my hammer?' or 'how many tools across all rooms?'"
          rows={2}
          className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-slate-400 resize-none"
        />
        <div className="flex items-center justify-between">
          <p className="text-xs text-slate-500">
            tier 1 is free (FULLTEXT); tier 2 needs Ollama; tier 3 is opt-in cloud (off by default)
          </p>
          <button
            type="submit"
            disabled={ask.isPending || !question.trim()}
            className="px-4 py-1.5 bg-slate-900 text-white rounded-md text-sm hover:bg-slate-700 disabled:opacity-50"
          >
            {ask.isPending ? "Thinking…" : "Ask"}
          </button>
        </div>
      </form>

      {ask.error && (
        <div className="px-3 py-2 text-sm rounded-md bg-red-50 text-red-700 border border-red-200">
          {ask.error.message}
        </div>
      )}

      {result && (
        <div className="space-y-3">
          <div className="border border-slate-200 rounded-md bg-white">
            <div className="px-3 py-2 border-b border-slate-100 flex items-center gap-2">
              <TierBadge tier={result.tier_used} />
              <span className="text-xs text-slate-500">
                {result.tool_calls.length} tool call{result.tool_calls.length === 1 ? "" : "s"}
              </span>
            </div>
            <pre className="px-3 py-3 text-sm whitespace-pre-wrap font-sans">{result.answer}</pre>
          </div>

          {result.tool_calls.length > 0 && (
            <details className="border border-slate-200 rounded-md bg-white">
              <summary className="px-3 py-2 cursor-pointer text-xs text-slate-600 hover:bg-slate-50">
                Tool call trace
              </summary>
              <div className="px-3 py-2 space-y-2">
                {result.tool_calls.map((tc, i) => (
                  <ToolCallEntry key={i} call={tc} onSelect={onSelect} />
                ))}
              </div>
            </details>
          )}

          {result.message && (
            <p className="text-xs text-slate-500 italic">{result.message}</p>
          )}
        </div>
      )}
    </div>
  );
}

function TierBadge({ tier }) {
  const colors = {
    search: "bg-emerald-100 text-emerald-700 border-emerald-200",
    local: "bg-blue-100 text-blue-700 border-blue-200",
    anthropic: "bg-purple-100 text-purple-700 border-purple-200",
    exhausted: "bg-amber-100 text-amber-700 border-amber-200",
  };
  return (
    <span
      className={
        "px-2 py-0.5 text-[10px] uppercase tracking-wide rounded border " +
        (colors[tier] || "bg-slate-100 text-slate-700 border-slate-200")
      }
    >
      {tier}
    </span>
  );
}

function ToolCallEntry({ call, onSelect }) {
  // Try to extract a node id from typical outputs so we can jump to it.
  const referencedId = findNodeId(call);
  return (
    <div className="text-xs font-mono">
      <div className="flex items-center gap-2">
        <span className={call.is_error ? "text-red-600" : "text-slate-700"}>
          {call.is_error ? "✗" : "→"} {call.tool}
        </span>
        <span className="text-slate-400 truncate">{JSON.stringify(call.input)}</span>
        {referencedId != null && (
          <button
            onClick={() => onSelect(referencedId)}
            className="ml-auto text-blue-600 hover:underline"
          >
            view #{referencedId}
          </button>
        )}
      </div>
      <pre className="mt-1 px-2 py-1 bg-slate-50 rounded text-[11px] whitespace-pre-wrap break-words">
        {call.output}
      </pre>
    </div>
  );
}

function findNodeId(call) {
  if (typeof call.input?.node_id === "number") return call.input.node_id;
  try {
    const out = JSON.parse(call.output);
    if (Array.isArray(out) && out.length > 0 && typeof out[0]?.id === "number")
      return out[0].id;
    if (out && typeof out.id === "number") return out.id;
  } catch {}
  return null;
}
