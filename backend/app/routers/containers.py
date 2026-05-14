from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import schemas, crud
from ..database import get_db

router = APIRouter(prefix="/containers", tags=["containers"])


@router.get("/", response_model=List[schemas.ContainerOut])
def read_containers(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.list_containers(db, skip=skip, limit=limit)


@router.post("/", response_model=schemas.ContainerOut, status_code=status.HTTP_201_CREATED)
def create_container(container_in: schemas.ContainerCreate, db: Session = Depends(get_db)):
    data = container_in.dict(exclude_unset=True)
    name = data.pop("name")
    return crud.create_container(db, name=name, **data)


@router.get("/{container_id}", response_model=schemas.ContainerOut)
def get_container(container_id: int, db: Session = Depends(get_db)):
    container = crud.get_container(db, container_id)
    if not container:
        raise HTTPException(status_code=404, detail="Container not found")
    return container


@router.put("/{container_id}", response_model=schemas.ContainerOut)
def update_container(container_id: int, container_in: schemas.ContainerUpdate, db: Session = Depends(get_db)):
    container = crud.get_container(db, container_id)
    if not container:
        raise HTTPException(status_code=404, detail="Container not found")
    return crud.update_container(db, container, **container_in.dict())


@router.delete("/{container_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_container(container_id: int, db: Session = Depends(get_db)):
    container = crud.get_container(db, container_id)
    if not container:
        raise HTTPException(status_code=404, detail="Container not found")
    crud.delete_container(db, container)
    return None


@router.get("/{container_id}/items", response_model=List[schemas.ItemOut])
def get_container_items(container_id: int, db: Session = Depends(get_db)):
    container = crud.get_container(db, container_id)
    if not container:
        raise HTTPException(status_code=404, detail="Container not found")
    return crud.list_items_in_container(db, container_id)
