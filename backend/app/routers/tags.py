from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Tag
from ..schemas import TagCreate, TagRef

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=List[TagRef])
def list_tags(
    q: Optional[str] = Query(None, description="Substring match on tag name."),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(Tag).order_by(Tag.name)
    if q:
        stmt = stmt.where(Tag.name.like(f"%{q}%"))
    stmt = stmt.offset(offset).limit(limit)
    return [TagRef.model_validate(t) for t in db.execute(stmt).scalars().all()]


@router.post("", response_model=TagRef)
def create_tag(body: TagCreate, response: Response, db: Session = Depends(get_db)):
    """Idempotent create: returns the existing tag if the name is already taken."""
    existing = db.execute(
        select(Tag).where(Tag.name == body.name)
    ).scalar_one_or_none()
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return TagRef.model_validate(existing)
    tag = Tag(name=body.name)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    response.status_code = status.HTTP_201_CREATED
    return TagRef.model_validate(tag)
