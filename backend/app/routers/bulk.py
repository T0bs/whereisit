from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..inbox import find_inbox, get_or_create_inbox
from ..models import Kind, Node
from ..routers.nodes import _to_out
from ..routers.search import _batch_paths
from ..schemas import NodeOut

router = APIRouter(tags=["bulk"])


class BulkAddRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    names: List[str] = Field(..., min_length=1, max_length=100)


class BulkAddResponse(BaseModel):
    inbox_id: int
    created: List[NodeOut]
    skipped: List[str] = Field(default_factory=list)


@router.post("/bulk-add", response_model=BulkAddResponse, status_code=status.HTTP_201_CREATED)
def bulk_add(body: BulkAddRequest, db: Session = Depends(get_db)) -> BulkAddResponse:
    cleaned: list[str] = []
    skipped: list[str] = []
    for raw in body.names:
        name = raw.strip()
        if not name:
            continue
        if len(name) > 255:
            skipped.append(raw)
            continue
        cleaned.append(name)

    if not cleaned:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "no non-empty names provided",
        )

    inbox = get_or_create_inbox(db)
    item_kind = db.execute(select(Kind).where(Kind.slug == "item")).scalar_one_or_none()
    if item_kind is None:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "kind 'item' is missing — run alembic upgrade head",
        )

    created_nodes: list[Node] = []
    for name in cleaned:
        node = Node(
            name=name,
            kind_id=item_kind.id,
            parent_id=inbox.id,
            can_contain=False,
        )
        db.add(node)
        created_nodes.append(node)
    db.commit()
    for node in created_nodes:
        db.refresh(node)

    return BulkAddResponse(
        inbox_id=inbox.id,
        created=[_to_out(n) for n in created_nodes],
        skipped=skipped,
    )


class CategoryOption(BaseModel):
    id: int
    name: str
    kind: str
    path: str


class BulkStateResponse(BaseModel):
    inbox_id: Optional[int] = None
    items: List[NodeOut] = Field(default_factory=list)
    categories: List[CategoryOption] = Field(default_factory=list)


@router.get("/bulk/state", response_model=BulkStateResponse)
def bulk_state(db: Session = Depends(get_db)) -> BulkStateResponse:
    """One snapshot for the BulkPanel: the inbox, its children, and all categories."""
    inbox = find_inbox(db)
    inbox_id = inbox.id if inbox is not None else None

    items: list[NodeOut] = []
    if inbox is not None:
        item_nodes = (
            db.execute(
                select(Node)
                .where(Node.parent_id == inbox.id)
                .order_by(Node.id)
                .options(joinedload(Node.kind), joinedload(Node.tags))
            )
            .unique()
            .scalars()
            .all()
        )
        items = [_to_out(n) for n in item_nodes]

    cat_stmt = (
        select(Node)
        .where(Node.can_contain.is_(True))
        .options(joinedload(Node.kind))
    )
    if inbox_id is not None:
        cat_stmt = cat_stmt.where(Node.id != inbox_id)
    cat_nodes = db.execute(cat_stmt).unique().scalars().all()

    paths_map = _batch_paths(db, [c.id for c in cat_nodes])
    categories = [
        CategoryOption(
            id=n.id,
            name=n.name,
            kind=n.kind.slug if n.kind else "",
            path=" / ".join(p.name for p in paths_map.get(n.id, [])),
        )
        for n in cat_nodes
    ]
    categories.sort(key=lambda c: c.path.lower())

    return BulkStateResponse(inbox_id=inbox_id, items=items, categories=categories)
