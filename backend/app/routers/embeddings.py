from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..ai import get_provider
from ..ai.embeddings import backfill
from ..ai.provider import LLMError
from ..database import get_db
from ..models import Embedding

router = APIRouter(prefix="/embeddings", tags=["embeddings"])


class BackfillRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: Optional[str] = None
    batch_size: int = Field(default=32, ge=1, le=128)
    force: bool = False


class BackfillResponse(BaseModel):
    model: str
    embedded: int
    skipped_fresh: int
    failed: int
    total_seen: int


class EmbeddingStatusResponse(BaseModel):
    model: str
    rows: int


@router.get("", response_model=list[EmbeddingStatusResponse])
def embedding_status(db: Session = Depends(get_db)):
    rows = db.execute(
        select(Embedding.model, func.count(Embedding.id)).group_by(Embedding.model)
    ).all()
    return [EmbeddingStatusResponse(model=m, rows=int(c)) for m, c in rows]


@router.post("/backfill", response_model=BackfillResponse)
def run_backfill(
    body: BackfillRequest, db: Session = Depends(get_db)
) -> BackfillResponse:
    provider = get_provider("local")
    try:
        report = backfill(
            db=db,
            provider=provider,
            model=body.model,
            batch_size=body.batch_size,
            force=body.force,
        )
    except LLMError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"embedding provider unavailable: {exc}",
        )
    return BackfillResponse(
        model=report.model,
        embedded=report.embedded,
        skipped_fresh=report.skipped_fresh,
        failed=report.failed,
        total_seen=report.total_seen,
    )
