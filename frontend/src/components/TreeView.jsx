import React, { useMemo, useState } from "react";
import { DndContext, useDraggable, useDroppable, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { useRootNodes, useChildren, useUpdateNode, useKinds } from "../queries";

const KIND_ICON = {
  building: "🏢",
  room: "🚪",
  cupboard: "🗄️",
  shelf: "📚",
  drawer: "🗃️",
  box: "📦",
  bag: "👜",
  item: "🔹",
  tool: "🔧",
  consumable: "🧴",
};

function kindIcon(slug) {
  return KIND_ICON[slug] || "•";
}

export default function TreeView({ selectedId, onSelect, onAddChild }) {
  const { data: roots = [], isLoading, error } = useRootNodes();
  const { data: kinds = [] } = useKinds();
  const kindById = useMemo(() => {
    const m = {};
    for (const k of kinds) m[k.id] = k;
    return m;
  }, [kinds]);
  const updateNode = useUpdateNode();
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));
  const [errorMsg, setErrorMsg] = useState(null);

  const handleDragEnd = async (event) => {
    setErrorMsg(null);
    const { active, over } = event;
    if (!over) return;
    const draggedId = active.id;
    const overId = over.id;
    if (draggedId === overId) return;
    const newParentId = overId === "__root__" ? null : overId;
    try {
      await updateNode.mutateAsync({ id: draggedId, body: { parent_id: newParentId } });
    } catch (e) {
      setErrorMsg(e.message || "move failed");
    }
  };

  if (isLoading) return <div className="p-4 text-sm text-slate-500">Loading…</div>;
  if (error) return <div className="p-4 text-sm text-red-600">Error: {error.message}</div>;

  return (
    <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
      <div className="py-2">
        {errorMsg && (
          <div className="mx-2 mb-2 px-2 py-1 text-xs rounded bg-red-50 text-red-700 border border-red-200">
            {errorMsg}
          </div>
        )}
        {roots.length === 0 ? (
          <p className="px-4 text-sm text-slate-500">No nodes yet. Click <em>+ Add root</em> to start.</p>
        ) : (
          roots.map((n) => (
            <TreeNode
              key={n.id}
              node={n}
              depth={0}
              selectedId={selectedId}
              onSelect={onSelect}
              onAddChild={onAddChild}
              kindById={kindById}
            />
          ))
        )}
        <RootDropZone />
      </div>
    </DndContext>
  );
}

function TreeNode({ node, depth, selectedId, onSelect, onAddChild, kindById }) {
  const [expanded, setExpanded] = useState(false);
  const { data: children = [] } = useChildren(expanded ? node.id : null);
  const kindSlug = kindById[node.kind_id]?.slug;

  const { attributes, listeners, setNodeRef: setDragRef, isDragging } = useDraggable({ id: node.id });
  const { setNodeRef: setDropRef, isOver } = useDroppable({
    id: node.id,
    disabled: !node.can_contain,
  });

  const combinedRef = (el) => {
    setDragRef(el);
    setDropRef(el);
  };

  const isSelected = selectedId === node.id;

  return (
    <div>
      <div
        ref={combinedRef}
        {...attributes}
        {...listeners}
        onClick={() => onSelect(node.id)}
        style={{ paddingLeft: 8 + depth * 16 }}
        className={
          "flex items-center gap-1 pr-2 py-1 text-sm cursor-pointer group select-none " +
          (isSelected ? "bg-slate-100 " : "hover:bg-slate-50 ") +
          (isOver && node.can_contain ? "ring-2 ring-inset ring-blue-400 " : "") +
          (isDragging ? "opacity-40 " : "")
        }
      >
        {node.can_contain ? (
          <button
            onClick={(e) => {
              e.stopPropagation();
              setExpanded((v) => !v);
            }}
            className="w-4 h-4 flex items-center justify-center text-slate-400 hover:text-slate-700"
            aria-label={expanded ? "collapse" : "expand"}
          >
            {expanded ? "▾" : "▸"}
          </button>
        ) : (
          <span className="w-4 h-4" />
        )}
        <span className="text-base leading-none">{kindIcon(kindSlug)}</span>
        <span className="truncate flex-1">{node.name}</span>
        {kindSlug && (
          <span className="text-[10px] uppercase tracking-wide text-slate-400">{kindSlug}</span>
        )}
        {node.can_contain && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onAddChild(node.id);
            }}
            className="opacity-0 group-hover:opacity-100 text-xs px-1.5 py-0.5 rounded text-slate-600 hover:bg-slate-200"
            title="Add child"
          >
            +
          </button>
        )}
      </div>
      {expanded && children.length > 0 && (
        <div>
          {children.map((c) => (
            <TreeNode
              key={c.id}
              node={c}
              depth={depth + 1}
              selectedId={selectedId}
              onSelect={onSelect}
              onAddChild={onAddChild}
              kindById={kindById}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function RootDropZone() {
  const { setNodeRef, isOver } = useDroppable({ id: "__root__" });
  return (
    <div
      ref={setNodeRef}
      className={
        "mx-2 mt-3 p-2 text-xs text-center border-2 border-dashed rounded " +
        (isOver ? "border-blue-400 text-blue-600 bg-blue-50" : "border-slate-200 text-slate-400")
      }
    >
      drop here to promote to root
    </div>
  );
}
