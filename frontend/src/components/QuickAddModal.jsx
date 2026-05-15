import React, { useState } from "react";
import { useKinds, useCreateNode } from "../queries";

export default function QuickAddModal({ parentId, onClose }) {
  const { data: kinds = [] } = useKinds();
  const createNode = useCreateNode();
  const [name, setName] = useState("");
  const [kind, setKind] = useState("item");
  const [canContain, setCanContain] = useState(false);
  const [description, setDescription] = useState("");
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    try {
      await createNode.mutateAsync({
        name: name.trim(),
        kind,
        parent_id: parentId ?? null,
        can_contain: canContain,
        description: description.trim() || undefined,
      });
      onClose();
    } catch (err) {
      setError(err.message || "create failed");
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/30 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-lg shadow-xl w-full max-w-md p-5 space-y-3"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold">
            Add {parentId ? "child" : "root"} node
          </h2>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700"
            aria-label="close"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3">
          <Field label="Name">
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              maxLength={255}
              className="w-full px-2.5 py-1.5 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
            />
          </Field>

          <Field label="Kind">
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value)}
              className="w-full px-2.5 py-1.5 border border-slate-300 rounded-md text-sm bg-white"
            >
              {kinds.map((k) => (
                <option key={k.id} value={k.slug}>
                  {k.label}
                </option>
              ))}
            </select>
          </Field>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={canContain}
              onChange={(e) => setCanContain(e.target.checked)}
            />
            <span>This node can contain other nodes (storage)</span>
          </label>

          <Field label="Description (optional)">
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full px-2.5 py-1.5 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
            />
          </Field>

          {error && (
            <p className="text-sm text-red-600">{error}</p>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-1.5 text-sm rounded-md border border-slate-300 hover:bg-slate-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={createNode.isPending || !name.trim()}
              className="px-3 py-1.5 text-sm rounded-md bg-slate-900 text-white hover:bg-slate-700 disabled:opacity-50"
            >
              {createNode.isPending ? "Adding…" : "Add"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block space-y-1">
      <span className="text-xs uppercase tracking-wide text-slate-500">{label}</span>
      {children}
    </label>
  );
}
