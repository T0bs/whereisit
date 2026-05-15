from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Kind, Node, Tag
from ..schemas import (
    KindRef,
    NodeCreate,
    NodeOut,
    NodeSummary,
    NodeUpdate,
    PropertyRef,
    TagRef,
    TreeNode,
)

router = APIRouter(prefix="/nodes", tags=["nodes"])


# ---------- helpers ----------


def _kind_or_404(db: Session, slug: str) -> Kind:
    kind = db.execute(select(Kind).where(Kind.slug == slug)).scalar_one_or_none()
    if kind is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown kind: {slug}")
    return kind


def _node_or_404(db: Session, node_id: int) -> Node:
    node = db.get(Node, node_id)
    if node is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"node {node_id} not found")
    return node


def _to_summary(node: Node) -> NodeSummary:
    return NodeSummary.model_validate(node)


def _to_out(node: Node) -> NodeOut:
    return NodeOut(
        id=node.id,
        name=node.name,
        kind=KindRef.model_validate(node.kind),
        parent_id=node.parent_id,
        can_contain=node.can_contain,
        description=node.description,
        quantity=node.quantity,
        width=node.width,
        height=node.height,
        depth=node.depth,
        weight=node.weight,
        gps_lat=node.gps_lat,
        gps_lng=node.gps_lng,
        created_at=node.created_at,
        updated_at=node.updated_at,
        tags=[TagRef.model_validate(t) for t in node.tags],
        properties=[
            PropertyRef(key=p.key.key, value=p.value, value_type=p.key.value_type)
            for p in node.properties
        ],
    )


def _is_descendant_of(db: Session, candidate_id: int, ancestor_id: int) -> bool:
    """True if `candidate_id` is `ancestor_id` itself or sits below it in the tree."""
    current_id: Optional[int] = candidate_id
    visited: set[int] = set()
    while current_id is not None and current_id not in visited:
        if current_id == ancestor_id:
            return True
        visited.add(current_id)
        node = db.get(Node, current_id)
        if node is None:
            return False
        current_id = node.parent_id
    return False


def _delete_subtree(db: Session, root_id: int) -> None:
    """Delete a node and all descendants, bottom-up to satisfy the parent_id FK."""
    stack = [root_id]
    all_ids: List[int] = []
    while stack:
        nid = stack.pop()
        all_ids.append(nid)
        child_ids = [
            r[0]
            for r in db.execute(select(Node.id).where(Node.parent_id == nid)).all()
        ]
        stack.extend(child_ids)
    for nid in reversed(all_ids):
        node = db.get(Node, nid)
        if node is not None:
            db.delete(node)


# ---------- list / create ----------


@router.get("", response_model=List[NodeSummary])
def list_nodes(
    parent: Optional[str] = Query(
        None,
        description="Filter by parent: 'root' for top-level, or an integer node id.",
    ),
    kind: Optional[str] = Query(None, description="Filter by kind slug."),
    tag: Optional[str] = Query(None, description="Filter by tag name."),
    q: Optional[str] = Query(None, description="Substring search on name."),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(Node)
    if parent is not None:
        if parent == "root":
            stmt = stmt.where(Node.parent_id.is_(None))
        else:
            try:
                pid = int(parent)
            except ValueError:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "parent must be 'root' or an integer node id",
                )
            stmt = stmt.where(Node.parent_id == pid)
    if kind is not None:
        stmt = stmt.join(Node.kind).where(Kind.slug == kind)
    if tag is not None:
        stmt = stmt.join(Node.tags).where(Tag.name == tag)
    if q is not None:
        stmt = stmt.where(Node.name.like(f"%{q}%"))
    stmt = stmt.order_by(Node.id).offset(offset).limit(limit)
    nodes = db.execute(stmt).scalars().unique().all()
    return [_to_summary(n) for n in nodes]


@router.post("", response_model=NodeOut, status_code=status.HTTP_201_CREATED)
def create_node(body: NodeCreate, db: Session = Depends(get_db)):
    kind = _kind_or_404(db, body.kind)
    if body.parent_id is not None:
        parent = _node_or_404(db, body.parent_id)
        if not parent.can_contain:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"parent {parent.id} does not accept children (can_contain=false)",
            )
    node = Node(
        name=body.name,
        kind_id=kind.id,
        parent_id=body.parent_id,
        can_contain=body.can_contain,
        description=body.description,
        quantity=body.quantity,
        width=body.width,
        height=body.height,
        depth=body.depth,
        weight=body.weight,
        gps_lat=body.gps_lat,
        gps_lng=body.gps_lng,
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return _to_out(node)


# ---------- single node ----------


@router.get("/{node_id}", response_model=NodeOut)
def get_node(node_id: int, db: Session = Depends(get_db)):
    return _to_out(_node_or_404(db, node_id))


@router.patch("/{node_id}", response_model=NodeOut)
def update_node(node_id: int, body: NodeUpdate, db: Session = Depends(get_db)):
    node = _node_or_404(db, node_id)
    data = body.model_dump(exclude_unset=True)

    if "kind" in data:
        node.kind_id = _kind_or_404(db, data.pop("kind")).id

    if "parent_id" in data:
        new_parent_id = data.pop("parent_id")
        if new_parent_id is not None:
            if new_parent_id == node.id:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, "node cannot be its own parent"
                )
            new_parent = _node_or_404(db, new_parent_id)
            if not new_parent.can_contain:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"parent {new_parent.id} does not accept children",
                )
            if _is_descendant_of(db, new_parent_id, node.id):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "reparenting would create a cycle",
                )
        node.parent_id = new_parent_id

    for k, v in data.items():
        setattr(node, k, v)

    db.commit()
    db.refresh(node)
    return _to_out(node)


@router.delete("/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_node(
    node_id: int,
    cascade: bool = Query(False, description="Delete the whole subtree."),
    db: Session = Depends(get_db),
):
    node = _node_or_404(db, node_id)
    has_children = (
        db.execute(select(Node.id).where(Node.parent_id == node_id).limit(1)).first()
        is not None
    )
    if has_children and not cascade:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "node has children; pass ?cascade=true to delete the subtree",
        )
    if cascade:
        _delete_subtree(db, node_id)
    else:
        db.delete(node)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- navigation ----------


@router.get("/{node_id}/children", response_model=List[NodeSummary])
def list_children(
    node_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    _node_or_404(db, node_id)
    stmt = (
        select(Node)
        .where(Node.parent_id == node_id)
        .order_by(Node.id)
        .offset(offset)
        .limit(limit)
    )
    return [_to_summary(n) for n in db.execute(stmt).scalars().all()]


@router.get("/{node_id}/path", response_model=List[NodeSummary])
def get_path(node_id: int, db: Session = Depends(get_db)):
    node = _node_or_404(db, node_id)
    chain: List[Node] = []
    current: Optional[Node] = node
    visited: set[int] = set()
    while current is not None and current.id not in visited:
        visited.add(current.id)
        chain.append(current)
        current = current.parent if current.parent_id is not None else None
    chain.reverse()
    return [_to_summary(n) for n in chain]


@router.get("/{node_id}/tree", response_model=TreeNode)
def get_tree(
    node_id: int,
    depth: int = Query(10, ge=0, le=50),
    db: Session = Depends(get_db),
):
    return _build_tree(db, _node_or_404(db, node_id), depth)


def _build_tree(db: Session, node: Node, depth: int) -> TreeNode:
    children: List[TreeNode] = []
    if depth > 0:
        child_nodes = (
            db.execute(
                select(Node).where(Node.parent_id == node.id).order_by(Node.id)
            )
            .scalars()
            .all()
        )
        children = [_build_tree(db, c, depth - 1) for c in child_nodes]
    return TreeNode(
        id=node.id,
        name=node.name,
        kind=KindRef.model_validate(node.kind),
        parent_id=node.parent_id,
        can_contain=node.can_contain,
        quantity=node.quantity,
        children=children,
    )
