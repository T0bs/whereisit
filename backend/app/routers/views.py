from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from .. import models

router = APIRouter(prefix="/views", tags=["views"])


@router.get("/", response_model=List[schemas.ViewOut])
def list_views(db: Session = Depends(get_db)):
    return db.query(models.View).all()


@router.get("/{view_id}", response_model=schemas.ViewOut)
def get_view(view_id: int, db: Session = Depends(get_db)):
    v = db.get(models.View, view_id)
    return v
