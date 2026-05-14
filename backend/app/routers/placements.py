from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import schemas, crud
from ..database import get_db

router = APIRouter(prefix="/placements", tags=["placements"])


@router.get("/", response_model=List[schemas.PlacementOut])
def read_placements(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.list_placements(db, skip=skip, limit=limit)


@router.post("/", response_model=schemas.PlacementOut, status_code=status.HTTP_201_CREATED)
def create_placement(p_in: schemas.PlacementCreate, db: Session = Depends(get_db)):
    # basic existence checks
    item = crud.get_item(db, p_in.item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    container = crud.get_container(db, p_in.container_id)
    if not container:
        raise HTTPException(status_code=404, detail="Container not found")
    return crud.create_placement(db, item_id=p_in.item_id, container_id=p_in.container_id, quantity=p_in.quantity)


@router.get("/{placement_id}", response_model=schemas.PlacementOut)
def get_placement(placement_id: int, db: Session = Depends(get_db)):
    p = crud.get_placement(db, placement_id)
    if not p:
        raise HTTPException(status_code=404, detail="Placement not found")
    return p


@router.delete("/{placement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_placement(placement_id: int, db: Session = Depends(get_db)):
    p = crud.get_placement(db, placement_id)
    if not p:
        raise HTTPException(status_code=404, detail="Placement not found")
    crud.delete_placement(db, p)
    return None
