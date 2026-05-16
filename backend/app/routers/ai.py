from __future__ import annotations

import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from sqlalchemy import select

from ..ai import get_provider
from ..ai.ask import cascade as ask_cascade
from ..ai.placement import PlacementInput, cascade, node_path
from ..database import get_db
from ..inbox import find_inbox
from ..models import Node

router = APIRouter(prefix="/ai", tags=["ai"])


def _cloud_enabled() -> bool:
    return os.getenv("WHEREISIT_CLOUD_ENABLED", "").lower() in ("1", "true", "yes", "on")


# ---------- request / response shapes ----------


class SuggestPlacementRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    description: str = Field(..., min_length=1, max_length=500)
    tags: List[str] = Field(default_factory=list, max_length=20)
    kind: Optional[str] = None
    confirm_remote: bool = False
    max_suggestions: int = Field(default=5, ge=1, le=20)


class PlacementSuggestion(BaseModel):
    node_id: int
    node_name: str
    path: str
    kind: Optional[str] = None
    reason: str
    score: float


class SuggestPlacementResponse(BaseModel):
    suggestions: List[PlacementSuggestion]
    tier_used: str
    cloud_enabled: bool
    message: Optional[str] = None


# ---------- routes ----------


@router.post("/suggest-placement", response_model=SuggestPlacementResponse)
def suggest_placement(
    body: SuggestPlacementRequest,
    db: Session = Depends(get_db),
) -> SuggestPlacementResponse:
    cloud_on = _cloud_enabled()

    if body.confirm_remote and not cloud_on:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "cloud_disabled",
                "message": "Server has WHEREISIT_CLOUD_ENABLED=false; cloud calls are not permitted.",
            },
        )

    local = get_provider("local")
    cloud = get_provider("anthropic") if (body.confirm_remote and cloud_on) else None

    result = cascade(
        db=db,
        placement=PlacementInput(
            description=body.description,
            tags=list(body.tags),
            kind=body.kind,
            max_suggestions=body.max_suggestions,
        ),
        local_provider=local,
        cloud_provider=cloud,
    )

    return SuggestPlacementResponse(
        suggestions=[
            PlacementSuggestion(
                node_id=c.node.id,
                node_name=c.node.name,
                path=node_path(c.node),
                kind=c.node.kind.slug if c.node.kind else None,
                reason=c.reason,
                score=round(c.score, 4),
            )
            for c in result.suggestions
        ],
        tier_used=result.tier_used,
        cloud_enabled=cloud_on,
        message=result.message,
    )


# ---------- /ai/ask ----------


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question: str = Field(..., min_length=1, max_length=1000)
    confirm_remote: bool = False
    max_iterations: int = Field(default=8, ge=1, le=20)


class ToolCallEntry(BaseModel):
    tool: str
    input: dict
    output: str
    is_error: bool = False


class AskResponse(BaseModel):
    answer: str
    tier_used: str
    tool_calls: List[ToolCallEntry] = Field(default_factory=list)
    cloud_enabled: bool
    message: Optional[str] = None


@router.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, db: Session = Depends(get_db)) -> AskResponse:
    cloud_on = _cloud_enabled()

    if body.confirm_remote and not cloud_on:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "cloud_disabled",
                "message": "Server has WHEREISIT_CLOUD_ENABLED=false; cloud calls are not permitted.",
            },
        )

    local = get_provider("local")
    cloud = get_provider("anthropic") if (body.confirm_remote and cloud_on) else None

    result = ask_cascade(
        db=db,
        question=body.question,
        local_provider=local,
        cloud_provider=cloud,
        max_iterations=body.max_iterations,
    )

    return AskResponse(
        answer=result.answer,
        tier_used=result.tier_used,
        tool_calls=[
            ToolCallEntry(
                tool=tc.tool, input=tc.input, output=tc.output, is_error=tc.is_error
            )
            for tc in result.tool_calls
        ],
        cloud_enabled=cloud_on,
        message=result.message,
    )


# ---------- /ai/suggest-categories + /ai/accept-categories (M13) ----------


class SuggestCategoriesRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    node_ids: List[int] = Field(..., min_length=1, max_length=100)
    confirm_remote: bool = False


class CategorySuggestion(BaseModel):
    node_id: int
    node_name: str
    suggested_parent_id: Optional[int] = None
    suggested_parent_name: Optional[str] = None
    suggested_parent_path: Optional[str] = None
    tier_used: str
    score: Optional[float] = None
    reason: Optional[str] = None


class SuggestCategoriesResponse(BaseModel):
    suggestions: List[CategorySuggestion]
    cloud_enabled: bool


@router.post("/suggest-categories", response_model=SuggestCategoriesResponse)
def suggest_categories(
    body: SuggestCategoriesRequest, db: Session = Depends(get_db)
) -> SuggestCategoriesResponse:
    cloud_on = _cloud_enabled()
    if body.confirm_remote and not cloud_on:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "cloud_disabled",
                "message": "Server has WHEREISIT_CLOUD_ENABLED=false; cloud calls are not permitted.",
            },
        )

    local = get_provider("local")
    cloud = get_provider("anthropic") if (body.confirm_remote and cloud_on) else None

    inbox = find_inbox(db)
    exclude_ids: set[int] = {inbox.id} if inbox is not None else set()

    nodes = (
        db.execute(select(Node).where(Node.id.in_(body.node_ids))).scalars().all()
    )
    nodes_by_id = {n.id: n for n in nodes}

    out: list[CategorySuggestion] = []
    for nid in body.node_ids:
        node = nodes_by_id.get(nid)
        if node is None:
            out.append(
                CategorySuggestion(
                    node_id=nid,
                    node_name="(unknown)",
                    tier_used="not_found",
                )
            )
            continue

        placement_input = PlacementInput(
            description=(node.description or node.name)[:500],
            tags=[t.name for t in node.tags],
            kind=node.kind.slug if node.kind else None,
            max_suggestions=1,
        )

        result = cascade(
            db=db,
            placement=placement_input,
            local_provider=local,
            cloud_provider=cloud,
            exclude_ids=exclude_ids,
        )

        if result.suggestions:
            top = result.suggestions[0]
            node.suggested_parent_id = top.node.id
            out.append(
                CategorySuggestion(
                    node_id=node.id,
                    node_name=node.name,
                    suggested_parent_id=top.node.id,
                    suggested_parent_name=top.node.name,
                    suggested_parent_path=node_path(top.node),
                    tier_used=result.tier_used,
                    score=round(top.score, 4),
                    reason=top.reason or None,
                )
            )
        else:
            node.suggested_parent_id = None
            out.append(
                CategorySuggestion(
                    node_id=node.id,
                    node_name=node.name,
                    tier_used=result.tier_used,
                )
            )
    db.commit()

    return SuggestCategoriesResponse(suggestions=out, cloud_enabled=cloud_on)


class AcceptCategoryEntry(BaseModel):
    node_id: int
    parent_id: int


class AcceptCategoriesRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    accepts: List[AcceptCategoryEntry] = Field(..., min_length=1, max_length=100)


class AcceptCategoryResult(BaseModel):
    node_id: int
    parent_id: Optional[int] = None
    ok: bool
    error: Optional[str] = None


class AcceptCategoriesResponse(BaseModel):
    results: List[AcceptCategoryResult]


@router.post("/accept-categories", response_model=AcceptCategoriesResponse)
def accept_categories(
    body: AcceptCategoriesRequest, db: Session = Depends(get_db)
) -> AcceptCategoriesResponse:
    from ..routers.nodes import _is_descendant_of, _node_or_404

    results: List[AcceptCategoryResult] = []

    for entry in body.accepts:
        savepoint = db.begin_nested()
        try:
            node = _node_or_404(db, entry.node_id)
            new_parent = _node_or_404(db, entry.parent_id)
            if new_parent.id == node.id:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, "node cannot be its own parent"
                )
            if not new_parent.can_contain:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"parent {new_parent.id} does not accept children",
                )
            if _is_descendant_of(db, new_parent.id, node.id):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "reparenting would create a cycle",
                )
            node.parent_id = new_parent.id
            node.suggested_parent_id = None
            savepoint.commit()
            results.append(
                AcceptCategoryResult(node_id=entry.node_id, parent_id=new_parent.id, ok=True)
            )
        except HTTPException as exc:
            savepoint.rollback()
            results.append(
                AcceptCategoryResult(
                    node_id=entry.node_id, ok=False, error=str(exc.detail)
                )
            )

    db.commit()
    return AcceptCategoriesResponse(results=results)
