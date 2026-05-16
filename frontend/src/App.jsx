import React, { useState } from "react";
import TreeView from "./components/TreeView";
import NodeDetail from "./components/NodeDetail";
import SearchPanel from "./components/SearchPanel";
import AskPanel from "./components/AskPanel";
import BulkPanel from "./components/BulkPanel";
import QuickAddModal from "./components/QuickAddModal";

const TABS = [
  { id: "detail", label: "Detail" },
  { id: "search", label: "Search" },
  { id: "ask", label: "Ask" },
  { id: "bulk", label: "Bulk" },
];

export default function App() {
  const [selectedId, setSelectedId] = useState(null);
  const [tab, setTab] = useState("detail");
  const [addOpen, setAddOpen] = useState(false);
  const [addParent, setAddParent] = useState(null);

  const openAdd = (parentId = null) => {
    setAddParent(parentId);
    setAddOpen(true);
  };
  const closeAdd = () => setAddOpen(false);

  const handleSelect = (id) => {
    setSelectedId(id);
    setTab("detail");
  };

  return (
    <div className="h-full flex flex-col">
      <header className="border-b border-slate-200 bg-white px-4 py-2 flex items-center justify-between">
        <h1 className="text-lg font-semibold tracking-tight">whereisit</h1>
        <button
          onClick={() => openAdd(null)}
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-700"
        >
          + Add root
        </button>
      </header>

      <div className="flex-1 min-h-0 flex">
        <aside className="w-80 border-r border-slate-200 bg-white overflow-auto scrollbar-thin">
          <TreeView
            selectedId={selectedId}
            onSelect={handleSelect}
            onAddChild={(id) => openAdd(id)}
          />
        </aside>

        <main className="flex-1 min-w-0 flex flex-col">
          <nav className="border-b border-slate-200 bg-white px-4 flex gap-1">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={
                  "px-3 py-2 text-sm border-b-2 -mb-px transition-colors " +
                  (tab === t.id
                    ? "border-slate-900 text-slate-900 font-medium"
                    : "border-transparent text-slate-500 hover:text-slate-900")
                }
              >
                {t.label}
              </button>
            ))}
          </nav>
          <div className="flex-1 min-h-0 overflow-auto scrollbar-thin p-4">
            {tab === "detail" && (
              <NodeDetail
                nodeId={selectedId}
                onSelect={handleSelect}
                onAddChild={(id) => openAdd(id)}
                onDeleted={() => setSelectedId(null)}
              />
            )}
            {tab === "search" && <SearchPanel onSelect={handleSelect} />}
            {tab === "ask" && <AskPanel onSelect={handleSelect} />}
            {tab === "bulk" && <BulkPanel onSelect={handleSelect} />}
          </div>
        </main>
      </div>

      {addOpen && <QuickAddModal parentId={addParent} onClose={closeAdd} />}
    </div>
  );
}
