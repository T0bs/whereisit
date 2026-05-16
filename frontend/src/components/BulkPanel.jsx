import React, { useMemo, useState } from "react";
import {
  useAcceptCategories,
  useBulkAdd,
  useBulkState,
  useSuggestCategories,
} from "../queries";

export default function BulkPanel({ onSelect }) {
  const { data, isLoading, error } = useBulkState();
  const bulkAdd = useBulkAdd();
  const suggest = useSuggestCategories();
  const accept = useAcceptCategories();

  const [namesInput, setNamesInput] = useState("");
  const [bulkError, setBulkError] = useState(null);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [overrides, setOverrides] = useState({});  // node_id → parent_id picked by user
  const [resultMsg, setResultMsg] = useState(null);

  const items = data?.items ?? [];
  const categories = data?.categories ?? [];

  const categoryById = useMemo(() => {
    const m = new Map();
    for (const c of categories) m.set(c.id, c);
    return m;
  }, [categories]);

  const toggle = (id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const toggleAll = () => {
    if (selectedIds.size === items.length) setSelectedIds(new Set());
    else setSelectedIds(new Set(items.map((i) => i.id)));
  };

  const handleBulkAdd = async (e) => {
    e.preventDefault();
    setBulkError(null);
    const names = namesInput
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    if (!names.length) {
      setBulkError("enter at least one name");
      return;
    }
    try {
      const result = await bulkAdd.mutateAsync(names);
      setNamesInput("");
      setResultMsg(`Added ${result.created.length} item${result.created.length === 1 ? "" : "s"} to Uncategorized.`);
    } catch (err) {
      setBulkError(err.message || "bulk-add failed");
    }
  };

  const handleSuggest = async () => {
    setResultMsg(null);
    if (selectedIds.size === 0) return;
    try {
      await suggest.mutateAsync({ node_ids: Array.from(selectedIds) });
    } catch (err) {
      setResultMsg(err.message || "suggest failed");
    }
  };

  const handleAccept = async () => {
    setResultMsg(null);
    const accepts = [];
    for (const id of selectedIds) {
      const item = items.find((i) => i.id === id);
      const parent_id =
        overrides[id] ?? item?.suggested_parent_id ?? null;
      if (parent_id != null) accepts.push({ node_id: id, parent_id });
    }
    if (!accepts.length) {
      setResultMsg("Nothing to accept — pick a category for each selected item.");
      return;
    }
    try {
      const result = await accept.mutateAsync({ accepts });
      const ok = result.results.filter((r) => r.ok).length;
      const failed = result.results.length - ok;
      setResultMsg(
        failed === 0
          ? `Moved ${ok} item${ok === 1 ? "" : "s"}.`
          : `Moved ${ok}; ${failed} failed — see browser console.`
      );
      if (failed > 0) console.warn("accept-categories failures:", result.results.filter((r) => !r.ok));
      setSelectedIds(new Set());
      setOverrides({});
    } catch (err) {
      setResultMsg(err.message || "accept failed");
    }
  };

  if (isLoading) return <p className="text-sm text-slate-500">Loading…</p>;
  if (error) return <p className="text-sm text-red-600">Error: {error.message}</p>;

  const allSelected = items.length > 0 && selectedIds.size === items.length;
  const hasSelection = selectedIds.size > 0;

  return (
    <div className="max-w-4xl space-y-6">
      {/* ─── bulk add ─── */}
      <section className="space-y-2">
        <h2 className="text-base font-semibold">Bulk add</h2>
        <p className="text-xs text-slate-500">
          One name per line. Each becomes a leaf <code className="px-1 bg-slate-100 rounded">kind=item</code> under the
          auto-created Uncategorized container.
        </p>
        <form onSubmit={handleBulkAdd} className="space-y-2">
          <textarea
            value={namesInput}
            onChange={(e) => setNamesInput(e.target.value)}
            rows={4}
            placeholder={"Claw hammer\nCordless drill\nSpare AAA batteries"}
            className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-slate-400"
          />
          {bulkError && <p className="text-sm text-red-600">{bulkError}</p>}
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={bulkAdd.isPending || !namesInput.trim()}
              className="px-4 py-1.5 text-sm rounded-md bg-slate-900 text-white hover:bg-slate-700 disabled:opacity-50"
            >
              {bulkAdd.isPending ? "Adding…" : "Add all"}
            </button>
          </div>
        </form>
      </section>

      {/* ─── uncategorized list ─── */}
      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold">
            Uncategorized ({items.length})
          </h2>
          <div className="flex gap-2">
            <button
              onClick={handleSuggest}
              disabled={!hasSelection || suggest.isPending}
              className="px-3 py-1.5 text-sm rounded-md border border-slate-300 hover:bg-slate-50 disabled:opacity-50"
            >
              {suggest.isPending ? "Suggesting…" : "Suggest for selected"}
            </button>
            <button
              onClick={handleAccept}
              disabled={!hasSelection || accept.isPending}
              className="px-3 py-1.5 text-sm rounded-md bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              {accept.isPending ? "Accepting…" : "Accept selected"}
            </button>
          </div>
        </div>

        {resultMsg && (
          <p className="text-sm text-slate-600 bg-slate-50 border border-slate-200 rounded px-3 py-2">{resultMsg}</p>
        )}

        {items.length === 0 ? (
          <p className="text-sm text-slate-500">Nothing uncategorized. Add items above to populate this list.</p>
        ) : categories.length === 0 ? (
          <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
            No categories (containers) exist yet. Add at least one storage location via the
            <em> + Add root</em> button (e.g. Garage, kind=room, <em>storage</em>) before suggesting categories.
          </p>
        ) : (
          <table className="w-full text-sm border border-slate-200 rounded-md bg-white">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-2 py-2 w-8">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    onChange={toggleAll}
                  />
                </th>
                <th className="px-2 py-2 text-left">Item</th>
                <th className="px-2 py-2 text-left">Category</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {items.map((item) => {
                const suggestion = item.suggested_parent_id;
                const override = overrides[item.id];
                const chosen = override ?? suggestion ?? "";
                const suggestionCat = suggestion ? categoryById.get(suggestion) : null;
                return (
                  <tr
                    key={item.id}
                    className={selectedIds.has(item.id) ? "bg-slate-50" : ""}
                  >
                    <td className="px-2 py-2">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(item.id)}
                        onChange={() => toggle(item.id)}
                      />
                    </td>
                    <td className="px-2 py-2">
                      <button
                        onClick={() => onSelect(item.id)}
                        className="text-left hover:underline"
                      >
                        {item.name}
                      </button>
                      <div className="text-[11px] text-slate-400">#{item.id}</div>
                    </td>
                    <td className="px-2 py-2">
                      <select
                        value={chosen}
                        onChange={(e) =>
                          setOverrides((o) => ({
                            ...o,
                            [item.id]: e.target.value ? Number(e.target.value) : null,
                          }))
                        }
                        className="w-full px-2 py-1 border border-slate-300 rounded text-sm bg-white"
                      >
                        <option value="">— pick category —</option>
                        {categories.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.path} ({c.kind})
                          </option>
                        ))}
                      </select>
                      {suggestionCat && override == null && (
                        <div className="text-[11px] text-emerald-600 mt-0.5">
                          suggested: {suggestionCat.path}
                        </div>
                      )}
                      {override != null && override !== suggestion && (
                        <div className="text-[11px] text-blue-600 mt-0.5">
                          override
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
