from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("/", response_model=List[schemas.Tag])
def list_tags(q: Optional[str] = Query(None, description="search query"), limit: int = Query(20), db: Session = Depends(get_db)):
    return crud.get_tags(db, q=q, limit=limit)


@router.post("/", response_model=schemas.Tag)
def create_tag(tag: schemas.TagCreate, db: Session = Depends(get_db)):
    existing = crud.get_tag_by_name(db, name=tag.name)
    if existing:
        raise HTTPException(status_code=400, detail="Tag already exists")
    return crud.create_tag(db, name=tag.name)


@router.delete("/{tag_id}")
def delete_tag(tag_id: int, db: Session = Depends(get_db)):
    tag = crud.get_tag(db, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    crud.delete_tag(db, tag)
    return {"ok": True}



@router.get("/{tag_id}", response_model=schemas.Tag)
def get_tag(tag_id: int, db: Session = Depends(get_db)):
    tag = crud.get_tag(db, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    return tag
