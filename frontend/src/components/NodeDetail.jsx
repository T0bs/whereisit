import React, { useState } from "react";
import {
  useNode,
  useChildren,
  useAddTag,
  useRemoveTag,
  useDeleteNode,
  useUpdateNode,
} from "../queries";

export default function NodeDetail({ nodeId, onSelect, onAddChild, onDeleted }) {
  if (nodeId == null) {
    return (
      <p className="text-sm text-slate-500">
        Select a node from the tree, or use Search / Ask to find one.
      </p>
    );
  }
  return <NodeDetailBody nodeId={nodeId} onSelect={onSelect} onAddChild={onAddChild} onDeleted={onDeleted} />;
}

function NodeDetailBody({ nodeId, onSelect, onAddChild, onDeleted }) {
  const { data: node, isLoading, error } = useNode(nodeId);
  const { data: children = [] } = useChildren(nodeId);
  const addTag = useAddTag();
  const removeTag = useRemoveTag();
  const updateNode = useUpdateNode();
  const deleteNode = useDeleteNode();

  const [tagInput, setTagInput] = useState("");
  const [editingName, setEditingName] = useState(false);
  const [draftName, setDraftName] = useState("");
  const [deleteErr, setDeleteErr] = useState(null);

  if (isLoading) return <p className="text-sm text-slate-500">Loading…</p>;
  if (error) return <p className="text-sm text-red-600">Error: {error.message}</p>;
  if (!node) return null;

  const startRename = () => {
    setDraftName(node.name);
    setEditingName(true);
  };
  const saveName = async () => {
    if (draftName.trim() && draftName !== node.name) {
      await updateNode.mutateAsync({ id: node.id, body: { name: draftName.trim() } });
    }
    setEditingName(false);
  };

  const handleAddTag = async (e) => {
    e.preventDefault();
    if (!tagInput.trim()) return;
    await addTag.mutateAsync({ nodeId: node.id, name: tagInput.trim() });
    setTagInput("");
  };

  const handleDelete = async (cascade) => {
    setDeleteErr(null);
    try {
      await deleteNode.mutateAsync({ id: node.id, cascade });
      onDeleted?.();
    } catch (err) {
      setDeleteErr(err.message || "delete failed");
    }
  };

  return (
    <div className="max-w-3xl space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          {editingName ? (
            <div className="flex items-center gap-2">
              <input
                value={draftName}
                onChange={(e) => setDraftName(e.target.value)}
                className="px-2 py-1 border border-slate-300 rounded text-lg font-semibold"
                onKeyDown={(e) => e.key === "Enter" && saveName()}
                autoFocus
              />
              <button onClick={saveName} className="text-sm text-slate-700 hover:underline">save</button>
              <button onClick={() => setEditingName(false)} className="text-sm text-slate-400 hover:underline">cancel</button>
            </div>
          ) : (
            <h2
              className="text-xl font-semibold truncate cursor-text"
              onClick={startRename}
              title="click to rename"
            >
              {node.name}
            </h2>
          )}
          <div className="text-xs text-slate-500 flex items-center gap-2 flex-wrap">
            <span className="px-1.5 py-0.5 rounded bg-slate-100 uppercase tracking-wide">
              {node.kind?.slug}
            </span>
            {node.can_contain && <span>storage</span>}
            <span>qty {node.quantity}</span>
            <span>id #{node.id}</span>
          </div>
        </div>
        <div className="flex gap-2 shrink-0">
          {node.can_contain && (
            <button
              onClick={() => onAddChild(node.id)}
              className="px-3 py-1.5 text-sm bg-slate-900 text-white rounded-md hover:bg-slate-700"
            >
              + child
            </button>
          )}
        </div>
      </div>

      {node.description && (
        <section className="text-sm text-slate-700 whitespace-pre-wrap border-l-4 border-slate-200 pl-3 py-1">
          {node.description}
        </section>
      )}

      <section className="space-y-2">
        <h3 className="text-xs uppercase tracking-wide text-slate-500">Tags</h3>
        <div className="flex flex-wrap gap-1.5">
          {node.tags.map((t) => (
            <span
              key={t.id}
              className="inline-flex items-center gap-1 px-2 py-0.5 text-xs bg-slate-100 rounded-full"
            >
              {t.name}
              <button
                onClick={() => removeTag.mutate({ nodeId: node.id, tagId: t.id })}
                className="text-slate-400 hover:text-red-600"
                aria-label={`remove ${t.name}`}
              >
                ×
              </button>
            </span>
          ))}
          <form onSubmit={handleAddTag} className="inline-flex items-center gap-1">
            <input
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              placeholder="add tag…"
              className="px-2 py-0.5 text-xs border border-slate-300 rounded"
            />
          </form>
        </div>
      </section>

      {node.properties.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-xs uppercase tracking-wide text-slate-500">Properties</h3>
          <table className="text-sm">
            <tbody>
              {node.properties.map((p) => (
                <tr key={p.key}>
                  <td className="pr-3 text-slate-500">{p.key}</td>
                  <td className="font-mono">{p.value}</td>
                  <td className="pl-3 text-[10px] text-slate-400 uppercase">{p.value_type}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {node.can_contain && (
        <section className="space-y-2">
          <h3 className="text-xs uppercase tracking-wide text-slate-500">
            Children ({children.length})
          </h3>
          {children.length === 0 ? (
            <p className="text-sm text-slate-400">Empty.</p>
          ) : (
            <ul className="border border-slate-200 rounded-md divide-y divide-slate-200 bg-white">
              {children.map((c) => (
                <li
                  key={c.id}
                  onClick={() => onSelect(c.id)}
                  className="px-3 py-1.5 text-sm cursor-pointer hover:bg-slate-50 flex items-center justify-between"
                >
                  <span className="truncate">{c.name}</span>
                  <span className="text-xs text-slate-400">id #{c.id}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <section className="pt-4 border-t border-slate-200">
        {deleteErr && <p className="mb-2 text-sm text-red-600">{deleteErr}</p>}
        <div className="flex gap-2">
          <button
            onClick={() => handleDelete(false)}
            className="px-3 py-1.5 text-sm rounded-md border border-red-300 text-red-700 hover:bg-red-50"
          >
            Delete
          </button>
          {node.can_contain && children.length > 0 && (
            <button
              onClick={() => handleDelete(true)}
              className="px-3 py-1.5 text-sm rounded-md border border-red-300 text-red-700 hover:bg-red-50"
            >
              Delete subtree
            </button>
          )}
        </div>
      </section>
    </div>
  );
}
