from __future__ import annotations

import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..ai import get_provider
from ..ai.placement import PlacementInput, cascade, node_path
from ..database import get_db

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
