from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Kind
from ..schemas import KindCreate, KindRef

router = APIRouter(prefix="/kinds", tags=["kinds"])


@router.get("", response_model=List[KindRef])
def list_kinds(
    q: Optional[str] = Query(None, description="Substring match on slug or label."),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(Kind).order_by(Kind.slug)
    if q:
        like = f"%{q}%"
        stmt = stmt.where((Kind.slug.like(like)) | (Kind.label.like(like)))
    stmt = stmt.offset(offset).limit(limit)
    return [KindRef.model_validate(k) for k in db.execute(stmt).scalars().all()]


@router.post("", response_model=KindRef)
def create_kind(body: KindCreate, response: Response, db: Session = Depends(get_db)):
    """Idempotent create: returns the existing kind if the slug is already taken."""
    existing = db.execute(
        select(Kind).where(Kind.slug == body.slug)
    ).scalar_one_or_none()
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return KindRef.model_validate(existing)
    label = body.label if body.label else body.slug.replace("_", " ").title()
    kind = Kind(slug=body.slug, label=label)
    db.add(kind)
    db.commit()
    db.refresh(kind)
    response.status_code = status.HTTP_201_CREATED
    return KindRef.model_validate(kind)
